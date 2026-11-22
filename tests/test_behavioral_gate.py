"""Automated tests for Gate 3: Lecture 5 Behavioral Model Testing (`behavioral_gate.py`).

Tests all 6 behavioral checks:
  1. `mft_canonical_profiles` (Minimum Functionality Test)
  2. `invariance_row_permutation` (Invariance / Metamorphic Test)
  3. `invariance_pseudonymous_key` (Contract Invariance Test)
  4. `directional_clicks_monotonicity` (Directional Expectation Test: -50% clicks)
  5. `directional_score_monotonicity` (Directional Expectation Test: -25pt score)
  6. `abstention_and_uncertainty_routing` (Safeguard & Abstention Test)

Also includes negative tests verifying that an inverted/broken model FAILS MFT and
Directional Expectation checks (preventing "Silent Success").
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from learnguard.data.features import build_feature_snapshot
from learnguard.data.ingestion import ingest_oulad
from learnguard.data.loading import load_snapshot_partitions
from learnguard.evaluation.data_gate import run_data_gate
from learnguard.evaluation.ml_gate import run_ml_gate
from learnguard.evaluation.scorecard import EVAL_SCHEMA_VERSION
from learnguard.ml.preprocessing import _prepare_split, build_preprocessing_artifact
from learnguard.ml.training import train_logistic_baseline

from deploy.ml.behavioral_gate import (
    BEHAVIORAL_SCORECARD_FILENAME,
    BEHAVIORAL_SUBJECT,
    MFT_MIN_RISK_GAP,
    _check_directional_clicks_monotonicity,
    _check_directional_score_monotonicity,
    _check_mft_canonical_profiles,
    publish_all_evaluation_scorecards,
    run_behavioral_gate,
)
from deploy.ml.data_simulator import generate_oulad_dataset


class _InvertedBrokenModel:
    """Deliberately inverted model that predicts higher risk for higher clicks & scores."""

    version = "broken-inverted-v1"
    feature_names = ("n_clicks_before_cutoff", "avg_score_submitted")

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        return np.zeros((len(X), 2), dtype=np.float64)

    def predict_positive_proba(self, X: pd.DataFrame) -> np.ndarray:
        clicks = pd.to_numeric(X["n_clicks_before_cutoff"], errors="coerce").fillna(0.0).to_numpy()
        scores = pd.to_numeric(X["avg_score_submitted"], errors="coerce").fillna(0.0).to_numpy()
        # Wrong direction: more clicks and higher score increase predicted risk!
        logits = 0.01 * clicks + 0.04 * scores - 2.5
        return 1.0 / (1.0 + np.exp(-np.clip(logits, -10.0, 10.0)))


def test_behavioral_gate_all_six_checks_pass_and_publish(tmp_path: Path) -> None:
    """Train a baseline LogisticRegression v2 model and verify all 6 behavioral checks pass."""
    raw_dir = tmp_path / "oulad_raw"
    artifacts_dir = tmp_path / "artifacts"
    ingestion_dir = artifacts_dir / "ingestion"
    snapshot_path = artifacts_dir / "snapshot" / "snapshot.parquet"

    generate_oulad_dataset(
        raw_dir, "baseline_no_drift", students_per_presentation=220, seed=42
    )
    ing = ingest_oulad(raw_dir, ingestion_dir)
    assert ing.status == "ok"
    snap = build_feature_snapshot(ingestion_dir, snapshot_path)

    run_id = "behav-test-01"
    pre = build_preprocessing_artifact(
        snap.snapshot_path, artifacts_dir, run_id=run_id
    )
    trained = train_logistic_baseline(
        snap.snapshot_path, pre.artifact_dir, artifacts_dir, run_id=run_id
    )

    card = run_behavioral_gate(
        trained.artifact_dir,
        pre.artifact_dir,
        snap.snapshot_path,
        run_id=run_id,
    )
    assert card.schema_version == EVAL_SCHEMA_VERSION
    assert card.subject == BEHAVIORAL_SUBJECT
    assert not card.has_failure()
    assert card.worst_status() == "pass"

    summary = card.summary()
    assert summary["total"] == 6
    assert summary["pass"] == 6
    assert summary["fail"] == 0

    check_ids = [chk.id for chk in card.checks]
    assert check_ids == [
        "mft_canonical_profiles",
        "invariance_row_permutation",
        "invariance_pseudonymous_key",
        "directional_clicks_monotonicity",
        "directional_score_monotonicity",
        "abstention_and_uncertainty_routing",
    ]

    by_id = {chk.id: chk for chk in card.checks}
    assert by_id["mft_canonical_profiles"].observed["risk_gap"] >= MFT_MIN_RISK_GAP
    assert (
        by_id["mft_canonical_profiles"].observed["pairwise_ordering_accuracy"]
        == 1.0
    )
    assert by_id["invariance_row_permutation"].observed["max_abs_diff"] <= 1e-12
    assert (
        by_id["directional_clicks_monotonicity"].observed["mean_risk_delta"]
        > 0.0
    )
    assert (
        by_id["directional_clicks_monotonicity"].observed[
            "individual_compliance_rate"
        ]
        >= 0.95
    )
    assert (
        by_id["directional_score_monotonicity"].observed["mean_risk_delta"]
        > 0.0
    )
    assert (
        by_id["directional_score_monotonicity"].observed[
            "individual_compliance_rate"
        ]
        >= 0.95
    )

    # Verify atomic publishing alongside DataGate and MLGate
    data_card = run_data_gate(snap.snapshot_path, None, run_id=run_id)
    ml_card = run_ml_gate(
        trained.artifact_dir,
        pre.artifact_dir,
        snap.snapshot_path,
        run_id=run_id,
    )
    eval_run_dir = publish_all_evaluation_scorecards(
        artifacts_dir, run_id, [data_card, ml_card, card]
    )
    assert (eval_run_dir / "eval_data.json").is_file()
    assert (eval_run_dir / "eval_ml.json").is_file()
    assert (eval_run_dir / BEHAVIORAL_SCORECARD_FILENAME).is_file()
    assert (eval_run_dir / "manifest.json").is_file()
    assert (eval_run_dir / "success.json").is_file()

    manifest = json.loads(
        (eval_run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == EVAL_SCHEMA_VERSION
    assert manifest["subjects"] == ["data", "ml", "behavioral"]


def test_behavioral_gate_rejects_inverted_broken_model(tmp_path: Path) -> None:
    """Negative test (M-07): an inverted model that penalizes engagement FAILS MFT and Directional checks."""
    raw_dir = tmp_path / "oulad_raw"
    ingestion_dir = tmp_path / "ingestion"
    snapshot_path = tmp_path / "snapshot" / "snapshot.parquet"

    generate_oulad_dataset(
        raw_dir, "baseline_no_drift", students_per_presentation=120, seed=42
    )
    ingest_oulad(raw_dir, ingestion_dir)
    snap = build_feature_snapshot(ingestion_dir, snapshot_path)

    selected = load_snapshot_partitions(snap.snapshot_path, ("validation",))
    prepared = _prepare_split("validation", selected.frame("validation"))
    broken_model = _InvertedBrokenModel()

    mft_chk = _check_mft_canonical_profiles(broken_model, prepared.X)
    assert mft_chk.status == "fail"
    assert mft_chk.observed["risk_gap"] < 0.0

    dir_clicks_chk = _check_directional_clicks_monotonicity(
        broken_model, prepared.X
    )
    assert dir_clicks_chk.status == "fail"
    assert dir_clicks_chk.observed["mean_risk_delta"] < 0.0

    dir_score_chk = _check_directional_score_monotonicity(
        broken_model, prepared.X
    )
    assert dir_score_chk.status == "fail"
    assert dir_score_chk.observed["mean_risk_delta"] < 0.0
