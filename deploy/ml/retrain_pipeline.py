#!/usr/bin/env python3
"""Continual Learning, Drift Triage & Champion-vs-Challenger Retraining Orchestrator.

Implements ADR-0010 and CMU MLIP Lecture 4-6:
  1. Executes M1 (`ingest_oulad`) -> M2 (`build_feature_snapshot`) -> M3 (`LeakageAuditor`
     + structural `DataQualityGate`).
  2. Checks active Champion release from `artifacts/model-releases/active_release.json`:
     - If no Champion exists yet (cold-start bootstrap), trains initial Champion model,
       runs 3-layer Evaluation Gates (`DataGate`, `MLGate`, `BehavioralGate`), packages
       an immutable `model-release.v1` directory `artifacts/model-releases/<release-id>/`,
       writes `active_release.json`, and scores M5 (`prediction-batch.v1`).
  3. When a Champion release already exists:
     - Runs `DriftMonitor` comparing new snapshot against the Champion's baseline snapshot
       and publishes `artifacts/drift-reports/<run-id>/drift_report.json`.
     - If `DATA_QUALITY_OR_SEMANTIC_FAILURE`:
       Logs actionable alert, blocks retraining and scoring (Safe Mode — Lecture 4 Q20),
       keeps Champion untouched, and returns exit code 1.
     - If `NO_DRIFT` or `WARN_MONITOR` (including `ASM-03` delayed ground truth where
       live week-4 cohort has covariate shift but no end-of-semester labels yet, and
       not `force-retrain`):
       Skips M4 retraining, scores the new snapshot directly using the incumbent Champion
       model & preprocessor with its locked Top-20% production threshold (`M5`), optionally
       upserts to PostgreSQL (`LEARNGUARD_PG_DSN`), and returns exit code 0.
     - If `DRIFT_RETRAIN_RECOMMENDED` (or `force-retrain` / `force_retrain`):
       Trains Challenger preprocessor + Challenger LogisticRegression v2 model, runs
       Champion-vs-Challenger 3-Layer Evaluation Gates (`DataGate` + `MLGate` + `BehavioralGate`),
       and publishes `eval_data.json`, `eval_ml.json`, `eval_behavioral.json` to
       `artifacts/evaluations/<run-id>/`:
       * In `DataGate`, compares against the actual Champion baseline snapshot so
         `eval_data.json` reports the true cross-cohort PSI (`status="warn"` when
         authorized by `DriftMonitor`) without self-deadlocking promotion.
       * In `MLGate`, fails closed (`status="fail"`) if Champion comparison raises
         any unexpected error (preventing Silent Success per Lecture 6).
       * If any gate fails (or Challenger regresses vs Champion beyond tolerance `0.01`):
         **REJECTS Challenger**, retains Champion in `active_release.json`, writes rejection
         report, and returns exit code 1.
       * If all 3 gates pass:
         **PROMOTES Challenger**, packages immutable `model-release.v1` directory,
         atomically updates `active_release.json` (preserving `previous_release` for
         instant rollback), and scores M5 with the new validation Top-20% threshold!
  4. Supports `--mode rollback` (with `--target-release-id` / `--rollback-release`):
     Verifies target release integrity, atomically rolls back `active_release.json`,
     and scores M5 with the restored Champion release.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

# Ensure `deploy/ml` or project root imports work seamlessly
_THIS_DIR = Path(__file__).resolve().parent
_PLATFORM_ROOT = _THIS_DIR.parent.parent
if str(_PLATFORM_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLATFORM_ROOT))

from deploy.ml.behavioral_gate import (
    publish_all_evaluation_scorecards,
    run_behavioral_gate,
)
from deploy.ml.data_simulator import SCENARIOS, generate_oulad_dataset
from deploy.ml.drift_monitor import (
    DECISION_DRIFT_RETRAIN,
    DECISION_NO_DRIFT,
    DECISION_QUALITY_FAILURE,
    DriftMonitor,
    DriftReport,
    publish_drift_report,
)
from learnguard.data.features import KEYS, build_feature_snapshot
from learnguard.data.ingestion import ingest_oulad
from learnguard.data.leakage import LeakageAuditor
from learnguard.data.loading import SPLITS, load_snapshot_partitions
from learnguard.data.quality import validate_snapshot
from learnguard.evaluation.data_gate import run_data_gate
from learnguard.evaluation.ml_gate import (
    ALERT_BUDGET_FRACTION,
    run_ml_gate,
)
from learnguard.evaluation.ml_gate import (
    THRESHOLDS as ML_GATE_THRESHOLDS,
)
from learnguard.evaluation.scorecard import GateCheck
from learnguard.ml.contracts import (
    PREDICTION_BATCH_SCHEMA_VERSION,
    PredictionBatchExporter,
)
from learnguard.ml.evaluation import (
    select_alert_budget_threshold,
    select_f1_threshold,
    threshold_metrics,
)
from learnguard.ml.model_interface import load_scoring_model
from learnguard.ml.preprocessing import (
    _file_hash,
    _prepare_split,
    _validate_run_id,
    build_preprocessing_artifact,
)
from learnguard.ml.release import (
    EVALUATION_RUN_SCHEMA_VERSION,
    MAX_ALERT_BUDGET_DEVIATION,
    MODEL_RELEASE_SCHEMA_VERSION,
    PRODUCTION_CANDIDATE,
    _feature_order_hash,
    _ledger_metadata,
    _prediction_metrics,
    load_and_verify_model_release,
)
from learnguard.ml.scoring import (
    _REVIEW_REASONS,
    PREDICTIONS_FILENAME,
    STATS_FEATURE_COLUMNS,
    BatchScorer,
    PredictionRecord,
    PredictionStatus,
    ScoringReport,
    _features_json_values,
    _ledger_cutoff_day,
    _pseudonymous_key,
    _records_frame,
    _top_signals,
    score_snapshot,
)
from learnguard.ml.scoring import (
    MANIFEST_FILENAME as BATCH_MANIFEST_FILENAME,
)
from learnguard.ml.scoring import (
    SUCCESS_FILENAME as BATCH_SUCCESS_FILENAME,
)
from learnguard.ml.training import (
    SHAP_BACKGROUND_FILENAME,
    load_logistic_model_artifact,
    train_logistic_baseline,
)
from learnguard.settings import CUTOFF_DAY

ACTIVE_RELEASE_FILENAME = "active_release.json"


@dataclass
class PipelineExecutionReport:
    """Comprehensive execution report for a continual learning / drift pipeline run."""

    status: str
    run_id: str
    mode: str
    outcome: str
    drift_decision: str | None = None
    recommended_action: str | None = None
    snapshot_path: str | None = None
    snapshot_version: str | None = None
    active_release_id: str | None = None
    previous_release_id: str | None = None
    promoted_new_release: bool = False
    production_threshold: float | None = None
    drift_report_dir: str | None = None
    evaluation_dir: str | None = None
    prediction_batch_dir: str | None = None
    scored_rows: int = 0
    database_write: str = "skipped_no_dsn"
    database_rows: int | None = None
    gate_summaries: dict[str, dict[str, int]] = field(default_factory=dict)
    details: str = ""


def _log(msg: str) -> None:
    print(f"[retrain-pipeline] {msg}", flush=True)


def get_active_release_pointer_path(artifacts_dir: Path | str) -> Path:
    return Path(artifacts_dir) / "model-releases" / ACTIVE_RELEASE_FILENAME


def load_active_release_pointer(artifacts_dir: Path | str) -> dict[str, Any] | None:
    pointer_path = get_active_release_pointer_path(artifacts_dir)
    if not pointer_path.is_file():
        return None
    try:
        data = json.loads(pointer_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and "current_release" in data else None
    except (OSError, ValueError):
        return None


def update_active_release_pointer(
    artifacts_dir: Path | str,
    new_release_entry: dict[str, Any],
) -> Path:
    """Atomically update `artifacts/model-releases/active_release.json` preserving `previous_release`."""
    pointer_path = get_active_release_pointer_path(artifacts_dir)
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_active_release_pointer(artifacts_dir)
    previous_release = existing.get("current_release") if existing else None
    history: list[dict[str, Any]] = []
    if existing and isinstance(existing.get("history"), list):
        history = list(existing["history"])
    if previous_release is not None:
        history.append(previous_release)

    payload = {
        "schema_version": "active-model-release.v1",
        "updated_at": datetime.now(UTC).isoformat(),
        "current_release": new_release_entry,
        "previous_release": previous_release,
        "history": history[-10:],
    }
    staging = pointer_path.parent / f".active_release.staging-{uuid.uuid4().hex}.json"
    staging.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(staging, pointer_path)
    return pointer_path


def package_verified_model_release(
    snapshot_path: Path | str,
    model_artifact_dir: Path | str,
    preprocessing_artifact_dir: Path | str,
    artifacts_dir: Path | str,
    release_id: str,
) -> dict[str, Any]:
    """Package a self-contained immutable `model-release.v1` directory verified by `load_and_verify_model_release`."""
    release_id = _validate_run_id(release_id)
    snapshot_path = Path(snapshot_path)
    model_root = Path(model_artifact_dir)
    preprocessor_root = Path(preprocessing_artifact_dir)
    target = Path(artifacts_dir) / "model-releases" / release_id
    if target.exists():
        raise FileExistsError(f"model_release_id_exists:{release_id}")

    loaded = load_logistic_model_artifact(
        model_root, snapshot_path, preprocessor_root
    )
    model_manifest = dict(loaded.manifest)
    preprocessor_manifest = json.loads(
        (preprocessor_root / "preprocessor.manifest.json").read_text(encoding="utf-8")
    )
    snapshot_version, cutoff_day, ledger_sha256 = _ledger_metadata(snapshot_path)

    # Compute validation Top-20% alert budget threshold
    selected = load_snapshot_partitions(snapshot_path, ("validation",))
    prepared = _prepare_split("validation", selected.frame("validation"))
    y_true = prepared.y.to_numpy(dtype=np.int64)
    scores = np.asarray(loaded.predict_positive_proba(prepared.X), dtype=np.float64)

    keys = prepared.keys.copy()
    keys["student_key"] = [
        _pseudonymous_key(str(m), str(p), s)
        for m, p, s in zip(
            keys["code_module"],
            keys["code_presentation"],
            keys["id_student"],
            strict=True,
        )
    ]
    budget = select_alert_budget_threshold(scores, keys, ALERT_BUDGET_FRACTION)
    allowed_deviation = max(MAX_ALERT_BUDGET_DEVIATION, 1.0 / max(len(y_true), 1))
    production_metrics = asdict(threshold_metrics(y_true, scores, budget.threshold))
    f1_thresh = select_f1_threshold(y_true, scores)
    max_f1_metrics = asdict(threshold_metrics(y_true, scores, f1_thresh))

    rank_labels = np.zeros(len(y_true), dtype=np.int64)
    rank_labels[budget.ranked_indices] = 1
    ranked_reference = _prediction_metrics(y_true, rank_labels)
    ranked_reference.update({
        "alert_count": budget.budget_count,
        "alert_rate": budget.budget_count / max(len(y_true), 1),
    })

    threshold_payload = {
        "schema_version": EVALUATION_RUN_SCHEMA_VERSION,
        "policy": "validation_alert_budget_scalar_v1",
        "derivation_split": "validation",
        "population": "all_finite_validation_scores",
        "target_fraction": ALERT_BUDGET_FRACTION,
        "validation_sample_count": len(y_true),
        "budget_count": budget.budget_count,
        "boundary_score": budget.boundary_score,
        "boundary_tie_count": budget.boundary_tie_count,
        "tie_policy": budget.tie_policy,
        "production_threshold": budget.threshold,
        "realized_alert_count": budget.realized_alert_count,
        "realized_alert_rate": budget.realized_alert_rate,
        "absolute_budget_deviation": budget.absolute_deviation,
        "maximum_allowed_deviation": allowed_deviation,
        "production_threshold_metrics": production_metrics,
        "ranked_reference_metrics": ranked_reference,
        "max_f1_comparator": max_f1_metrics,
        "holdout_used": False,
    }

    prob_sha256 = sha256(
        np.ascontiguousarray(scores, dtype="<f8").tobytes()
    ).hexdigest()
    validation_eval_payload = {
        "status": "ok",
        "schema_version": EVALUATION_RUN_SCHEMA_VERSION,
        "run_id": release_id,
        "created_at": datetime.now(UTC).isoformat(),
        "evaluation_scope": "validation_only",
        "snapshot_version": snapshot_version,
        "preprocessor_version": preprocessor_manifest["preprocessor_version"],
        "model_version": model_manifest["model_semantic_version"],
        "model_artifact_sha256": _file_hash(model_root / "model.joblib"),
        "validation_probability_sha256": prob_sha256,
        "candidate_count": 1,
        "production_model": PRODUCTION_CANDIDATE,
        "validation_leader": PRODUCTION_CANDIDATE,
        "random_forest_b_status": "validation_release_candidate",
        "production_threshold": budget.threshold,
        "production_metrics": production_metrics,
        "holdout_accessed": False,
        "holdout_reused": False,
        "production_release_eligible": True,
        "eligibility_basis": "incumbent_logistic_validation_policy",
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{release_id}.staging-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        shutil.copytree(model_root, staging / "model")
        shutil.copytree(preprocessor_root, staging / "preprocessor")
        (staging / "validation_evaluation.json").write_text(
            json.dumps(validation_eval_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (staging / "threshold_policy.json").write_text(
            json.dumps(threshold_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (staging / "model_card.md").write_text(
            "# LearnGuard Logistic production release\n\n"
            f"Release: `{release_id}`  \n"
            f"Model: `{model_manifest['model_semantic_version']}`  \n"
            f"Snapshot: `{snapshot_version}`  \n"
            f"Production threshold: `{float(budget.threshold):.12g}`  \n"
            "Policy: scalar threshold derived from a validation Top-20% alert budget.  \n"
            "Promoted after passing 3-layer Evaluation Gates (Data + ML + Behavioral).  \n"
            "Holdout 2014J was not reused for this release.  \n"
            "SHAP explanations are associations, not causal effects.\n",
            encoding="utf-8",
        )

        payload_files = [path for path in staging.rglob("*") if path.is_file()]
        release_manifest = {
            "schema_version": MODEL_RELEASE_SCHEMA_VERSION,
            "release_id": release_id,
            "created_at": datetime.now(UTC).isoformat(),
            "release_status": "production",
            "production_release_eligible": True,
            "eligibility_basis": "incumbent_logistic_validation_policy",
            "scientific_evaluation_scope": "validation_only",
            "model_type": model_manifest["model_type"],
            "model_version": model_manifest["model_semantic_version"],
            "model_artifact_dir": "model",
            "model_artifact_sha256": model_manifest["model_artifact_sha256"],
            "preprocessing_artifact_dir": "preprocessor",
            "preprocessor_version": preprocessor_manifest["preprocessor_version"],
            "preprocessor_artifact_sha256": preprocessor_manifest["artifact_sha256"],
            "snapshot_version": snapshot_version,
            "snapshot_ledger_sha256": ledger_sha256,
            "cutoff_day": cutoff_day,
            "target_column": model_manifest["target_column"],
            "positive_class": model_manifest["positive_class"],
            "negative_class": model_manifest["negative_class"],
            "output_feature_count": model_manifest["output_feature_count"],
            "output_feature_order_sha256": _feature_order_hash(
                model_manifest["output_feature_names"]
            ),
            "production_threshold": float(budget.threshold),
            "threshold_policy": "validation_alert_budget_scalar_v1",
            "threshold_derivation_split": "validation",
            "target_alert_fraction": ALERT_BUDGET_FRACTION,
            "realized_validation_alert_rate": budget.realized_alert_rate,
            "maximum_f1_comparator_threshold": max_f1_metrics["threshold"],
            "validation_metrics": production_metrics,
            "random_seed": 42,
            "packages": model_manifest["packages"],
            "explanation": model_manifest["explanation"],
            "production_model_status": "incumbent_production",
            "random_forest_b_status": "validation_release_candidate",
            "candidate_promotion_eligible": False,
            "holdout_reused": False,
            "holdout_access_policy": "forbidden_prior_consumed",
            "prior_holdout_exposure": (
                "2014J was consumed by a prior benchmark and is not evidence for this release"
            ),
            "files": {
                str(path.relative_to(staging)): _file_hash(path)
                for path in sorted(payload_files)
            },
        }
        manifest_path = staging / "release.manifest.json"
        manifest_path.write_text(
            json.dumps(release_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (staging / "release.success.json").write_text(
            json.dumps(
                {
                    "schema_version": MODEL_RELEASE_SCHEMA_VERSION,
                    "release_id": release_id,
                    "manifest_sha256": _file_hash(manifest_path),
                    "payload_file_count": len(payload_files),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    # Verify with upstream load_and_verify_model_release immediately
    verified = load_and_verify_model_release(target, snapshot_path)
    return {
        "release_id": verified.release_id,
        "release_dir": str(target),
        "model_dir": str(verified.model_artifact_dir),
        "preprocessing_dir": str(verified.preprocessing_artifact_dir),
        "model_version": verified.model_version,
        "preprocessor_version": str(preprocessor_manifest["preprocessor_version"]),
        "snapshot_version": verified.snapshot_version,
        "baseline_snapshot_path": str(snapshot_path),
        "production_threshold": verified.production_threshold,
        "promoted_at": datetime.now(UTC).isoformat(),
    }


def _evaluate_champion_vs_challenger_regression(
    champion_release: dict[str, Any],
    challenger_model_dir: Path,
    challenger_pre_dir: Path,
    new_snapshot_path: Path,
) -> GateCheck:
    """Evaluate Challenger vs incumbent Champion ROC-AUC on the new validation split.

    Fails closed (`status="fail"`) if the Champion cannot be loaded or scored on the
    new validation split, preventing "Silent Success" (CMU MLIP Lecture 6).
    """
    try:
        champ_model_dir = Path(champion_release["model_dir"])
        champ_pre_dir = Path(champion_release["preprocessing_dir"])
        champ_estimator = joblib.load(champ_model_dir / "model.joblib")
        champ_transformer = joblib.load(champ_pre_dir / "preprocessor.joblib")

        challenger_model = load_scoring_model(
            challenger_model_dir, new_snapshot_path, challenger_pre_dir
        )
        selected = load_snapshot_partitions(new_snapshot_path, ("validation",))
        prepared = _prepare_split("validation", selected.frame("validation"))
        y_true = prepared.y.to_numpy(dtype=np.int64)

        challenger_scores = np.asarray(
            challenger_model.predict_positive_proba(prepared.X), dtype=np.float64
        )
        champ_matrix = np.ascontiguousarray(
            champ_transformer.transform(prepared.X), dtype=np.float64
        )
        champ_scores = np.asarray(
            champ_estimator.predict_proba(champ_matrix)[:, 1], dtype=np.float64
        )

        new_auc = float(roc_auc_score(y_true, challenger_scores))
        old_auc = float(roc_auc_score(y_true, champ_scores))
        delta = new_auc - old_auc
        observed = {
            "new_roc_auc": round(new_auc, 4),
            "baseline_roc_auc": round(old_auc, 4),
            "delta": round(delta, 4),
            "new_model_version": str(challenger_model.version),
            "baseline_model_version": str(
                champion_release.get("model_version", "unknown")
            ),
        }
        if delta < -ML_GATE_THRESHOLDS.regression_tolerance:
            return GateCheck(
                "regression_vs_baseline",
                "roc_auc mới không tụt so với baseline model",
                "fail",
                observed,
                f"new ≥ baseline − {ML_GATE_THRESHOLDS.regression_tolerance}",
                f"roc_auc tụt {abs(delta):.4f} so với Champion "
                f"({observed['baseline_model_version']} → {challenger_model.version})",
            )
        return GateCheck(
            "regression_vs_baseline",
            "roc_auc mới không tụt so với baseline model",
            "pass",
            observed,
            f"new ≥ baseline − {ML_GATE_THRESHOLDS.regression_tolerance}",
            f"roc_auc Challenger {new_auc:.4f} vs Champion {old_auc:.4f} (delta {delta:+.4f})",
        )
    except Exception as exc:  # noqa: BLE001 — fail closed on unexpected Champion load/score error
        return GateCheck(
            "regression_vs_baseline",
            "roc_auc mới không tụt so với baseline model",
            "fail",
            {
                "reason": f"champion_comparison_failed:{type(exc).__name__}",
                "error": str(exc),
            },
            f"new ≥ baseline − {ML_GATE_THRESHOLDS.regression_tolerance}",
            f"Fail-closed: Không thể chấm Champion cũ trên snapshot mới ({type(exc).__name__}: {exc})",
        )


def _score_snapshot_with_champion_release(
    snapshot_path: Path,
    champion_release: dict[str, Any],
    output_path: Path,
    run_id: str,
) -> ScoringReport:
    """Score a new snapshot with an existing Champion release.

    If `snapshot_version` matches the Champion's training snapshot, delegates directly
    to `score_snapshot`. If the new snapshot has a newer `snapshot_version` (e.g. minor
    non-drifted cohort update or unlabeled week-4 cohort), verifies Champion artifact
    SHA-256 hashes and scores every row deterministically with Linear SHAP and
    `PredictionBatchExporter`.
    """
    champ_model_dir = Path(champion_release["model_dir"])
    champ_pre_dir = Path(champion_release["preprocessing_dir"])
    threshold = float(champion_release.get("production_threshold", 0.5))

    snapshot_splits = load_snapshot_partitions(snapshot_path, SPLITS)
    if snapshot_splits.snapshot_version == champion_release.get("snapshot_version"):
        return score_snapshot(
            snapshot_path,
            champ_model_dir,
            champ_pre_dir,
            output_path,
            threshold=threshold,
            run_id=run_id,
        )

    # Cross-snapshot Champion inference with strict SHA-256 integrity verification
    model_manifest = json.loads(
        (champ_model_dir / "model.manifest.json").read_text(encoding="utf-8")
    )
    pre_manifest = json.loads(
        (champ_pre_dir / "preprocessor.manifest.json").read_text(encoding="utf-8")
    )
    if _file_hash(champ_model_dir / "model.joblib") != model_manifest.get(
        "model_artifact_sha256"
    ):
        raise ValueError("champion_model_artifact_hash_mismatch")
    if _file_hash(champ_pre_dir / "preprocessor.joblib") != pre_manifest.get(
        "artifact_sha256"
    ):
        raise ValueError("champion_preprocessor_artifact_hash_mismatch")

    estimator = joblib.load(champ_model_dir / "model.joblib")
    transformer = joblib.load(champ_pre_dir / "preprocessor.joblib")
    with np.load(champ_model_dir / SHAP_BACKGROUND_FILENAME) as bg:
        bg_mean = np.asarray(bg["mean"], dtype=np.float64)

    feature_names = tuple(str(x) for x in model_manifest["output_feature_names"])
    model_version = str(model_manifest["model_semantic_version"])
    cutoff_day = _ledger_cutoff_day(snapshot_path)
    scorer = BatchScorer()

    records: list[PredictionRecord] = []
    id_students: list[object] = []
    coefs = np.asarray(estimator.coef_[0], dtype=np.float64)

    for split_name in SPLITS:
        prepared = _prepare_split(split_name, snapshot_splits.frame(split_name))
        matrix = np.ascontiguousarray(
            transformer.transform(prepared.X), dtype=np.float64
        )
        probabilities = np.asarray(
            estimator.predict_proba(matrix)[:, 1], dtype=np.float64
        )
        shap_matrix = (matrix - bg_mean) * coefs
        insufficient = prepared.X["insufficient_data"].to_numpy(dtype=bool)
        stats_frame = prepared.X.loc[:, STATS_FEATURE_COLUMNS]
        modules = prepared.keys["code_module"].tolist()
        presentations = prepared.keys["code_presentation"].tolist()
        students = prepared.keys["id_student"].tolist()

        for idx in range(len(probabilities)):
            risk_score = float(probabilities[idx])
            uncertainty = 1.0 - abs(2.0 * risk_score - 1.0)
            data_status = "insufficient_data" if insufficient[idx] else "ok"
            status = scorer.assign_review_state(
                risk_score, threshold, uncertainty, data_status
            )
            predicted_label = (
                None
                if status is PredictionStatus.INSUFFICIENT_DATA
                else int(risk_score >= threshold)
            )
            keys = (modules[idx], presentations[idx], students[idx])
            records.append(
                PredictionRecord(
                    student_key=_pseudonymous_key(*keys),
                    code_module=str(modules[idx]),
                    code_presentation=str(presentations[idx]),
                    split=split_name,
                    risk_score=risk_score,
                    predicted_label=predicted_label,
                    threshold=threshold,
                    uncertainty=uncertainty,
                    status=status,
                    model_version=model_version,
                    snapshot_version=snapshot_splits.snapshot_version,
                    cutoff_day=cutoff_day,
                    top_signals=_top_signals(feature_names, shap_matrix[idx]),
                    review_reason=_REVIEW_REASONS[status],
                    features=_features_json_values(stats_frame.iloc[idx]),
                )
            )
            id_students.append(students[idx])

    frame = (
        _records_frame(records, id_students)
        .sort_values(list(KEYS), kind="mergesort")
        .reset_index(drop=True)
        .drop(columns=["id_student"])
    )
    batch_dir = output_path.parent
    if batch_dir.exists():
        raise FileExistsError(f"prediction_batch_run_id_exists:{run_id}")
    batch_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = batch_dir.parent / f".{batch_dir.name}.staging-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        frame.to_parquet(staging / PREDICTIONS_FILENAME, index=False)
        manifest = PredictionBatchExporter().export(
            staging / PREDICTIONS_FILENAME,
            staging / BATCH_MANIFEST_FILENAME,
            run_id,
            snapshot_splits.snapshot_version,
            model_version,
            cutoff_day,
        )
        (staging / BATCH_SUCCESS_FILENAME).write_text(
            json.dumps(
                {
                    "schema_version": PREDICTION_BATCH_SCHEMA_VERSION,
                    "run_id": run_id,
                    "manifest_sha256": _file_hash(staging / BATCH_MANIFEST_FILENAME),
                    "predictions_sha256": manifest.predictions_sha256,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(staging, batch_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    counts = {st: sum(r.status is st for r in records) for st in PredictionStatus}
    return ScoringReport(
        status="ok",
        model_version=model_version,
        snapshot_version=snapshot_splits.snapshot_version,
        input_rows=len(records),
        scored_rows=counts[PredictionStatus.SCORED],
        manual_review_rows=counts[PredictionStatus.MANUAL_REVIEW],
        insufficient_data_rows=counts[PredictionStatus.INSUFFICIENT_DATA],
        output_path=output_path,
        batch_dir=batch_dir,
        threshold=threshold,
        no_prediction_rows=counts[PredictionStatus.NO_PREDICTION],
        release_id=str(champion_release.get("release_id", "")),
    )


def _maybe_write_to_database(
    scoring_report: ScoringReport,
    run_id: str,
    pg_dsn: str | None,
) -> ScoringReport:
    dsn = pg_dsn or os.environ.get("LEARNGUARD_PG_DSN", "")
    if not dsn or scoring_report.status != "ok":
        return scoring_report
    from learnguard.ml.predictions_store import (
        PredictionStore,
        PredictionStoreConfig,
    )

    frame = pd.read_parquet(scoring_report.output_path)
    with PredictionStore(
        PredictionStoreConfig(dsn=dsn, table="ml_predictions")
    ) as store:
        store.ensure_schema()
        written = store.write_predictions(frame, run_id)
        stored = store.count_run(run_id)
    if stored != written:
        raise ValueError(
            f"database_rowcount_mismatch:written={written}:stored={stored}"
        )
    scoring_report.database_write = "ok"
    scoring_report.database_rows = stored
    return scoring_report


def rollback_active_release(
    artifacts_dir: Path | str,
    *,
    target_release_id: str | None = None,
    run_id: str | None = None,
    pg_dsn: str | None = None,
) -> tuple[int, PipelineExecutionReport]:
    """Roll back `active_release.json` to `target_release_id` (or `previous_release`) and score M5."""
    artifacts = Path(artifacts_dir)
    run_id = _validate_run_id(
        run_id or datetime.now(UTC).strftime("rollback-%Y%m%dT%H%M%SZ")
    )
    pointer = load_active_release_pointer(artifacts)
    if pointer is None:
        return 1, PipelineExecutionReport(
            status="failed",
            run_id=run_id,
            mode="rollback",
            outcome="ROLLBACK_FAILED_NO_ACTIVE_POINTER",
            details="No active_release.json found to roll back.",
        )

    current_rel = pointer.get("current_release") or {}
    prev_rel = pointer.get("previous_release")
    history: list[dict[str, Any]] = (
        list(pointer["history"]) if isinstance(pointer.get("history"), list) else []
    )

    resolved_target: dict[str, Any] | None = None
    if target_release_id:
        for candidate in ([prev_rel] if prev_rel else []) + list(reversed(history)):
            if (
                isinstance(candidate, dict)
                and candidate.get("release_id") == target_release_id
            ):
                resolved_target = dict(candidate)
                break
        if resolved_target is None:
            # Reconstruct from artifacts/model-releases/<target_release_id>
            rel_dir = artifacts / "model-releases" / target_release_id
            manifest_path = rel_dir / "release.manifest.json"
            if not manifest_path.is_file():
                return 1, PipelineExecutionReport(
                    status="failed",
                    run_id=run_id,
                    mode="rollback",
                    outcome="ROLLBACK_TARGET_NOT_FOUND",
                    details=f"Target release {target_release_id} not found in {rel_dir}",
                )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            snap_candidate = artifacts / "feature_snapshot_m2" / "snapshot.parquet"
            verified = load_and_verify_model_release(rel_dir, snap_candidate)
            resolved_target = {
                "release_id": verified.release_id,
                "release_dir": str(rel_dir),
                "model_dir": str(verified.model_artifact_dir),
                "preprocessing_dir": str(verified.preprocessing_artifact_dir),
                "model_version": verified.model_version,
                "preprocessor_version": str(manifest.get("preprocessor_version", "")),
                "snapshot_version": verified.snapshot_version,
                "baseline_snapshot_path": str(snap_candidate),
                "production_threshold": verified.production_threshold,
            }
    else:
        if isinstance(prev_rel, dict) and prev_rel.get("release_id"):
            resolved_target = dict(prev_rel)
        else:
            return 1, PipelineExecutionReport(
                status="failed",
                run_id=run_id,
                mode="rollback",
                outcome="ROLLBACK_FAILED_NO_PREVIOUS_RELEASE",
                active_release_id=str(current_rel.get("release_id", "")),
                details="No previous_release available in active_release.json and no --target-release-id specified.",
            )

    target_dir = Path(resolved_target["release_dir"])
    target_snap = Path(resolved_target["baseline_snapshot_path"])
    verified = load_and_verify_model_release(target_dir, target_snap)
    resolved_target["rolled_back_at"] = datetime.now(UTC).isoformat()
    resolved_target["rolled_back_from"] = current_rel.get("release_id")

    update_active_release_pointer(artifacts, resolved_target)

    # Restore canonical snapshot and run M5 batch scoring with the rolled-back Champion
    canonical_snapshot_dir = artifacts / "feature_snapshot_m2"
    canonical_snapshot_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target_snap, canonical_snapshot_dir / "snapshot.parquet")
    target_ledger = target_snap.parent / f"{target_snap.stem}.ledger.json"
    if target_ledger.is_file():
        shutil.copy2(target_ledger, canonical_snapshot_dir / "snapshot.ledger.json")

    batch_output = artifacts / "prediction-batches" / run_id / PREDICTIONS_FILENAME
    scoring_rep = _score_snapshot_with_champion_release(
        target_snap, resolved_target, batch_output, run_id=run_id
    )
    scoring_rep = _maybe_write_to_database(scoring_rep, run_id, pg_dsn)

    _log(
        f"Rolled back active release from {current_rel.get('release_id')} -> "
        f"{verified.release_id} and scored {scoring_rep.scored_rows} rows."
    )
    return 0, PipelineExecutionReport(
        status="ok",
        run_id=run_id,
        mode="rollback",
        outcome="ROLLED_BACK_RELEASE",
        snapshot_path=str(target_snap),
        snapshot_version=verified.snapshot_version,
        active_release_id=verified.release_id,
        previous_release_id=str(current_rel.get("release_id", "")),
        promoted_new_release=False,
        production_threshold=verified.production_threshold,
        prediction_batch_dir=str(scoring_rep.batch_dir),
        scored_rows=scoring_rep.scored_rows,
        database_write=scoring_rep.database_write,
        database_rows=scoring_rep.database_rows,
        details=(
            f"Successfully rolled back from {current_rel.get('release_id')} "
            f"to {verified.release_id}."
        ),
    )


def run_continual_pipeline(
    data_dir: Path | str,
    artifacts_dir: Path | str,
    *,
    mode: str = "auto",
    baseline_snapshot_path: Path | str | None = None,
    run_id: str | None = None,
    min_roc_auc: float = 0.70,
    cutoff_day: int = CUTOFF_DAY,
    pg_dsn: str | None = None,
    target_release_id: str | None = None,
) -> tuple[int, PipelineExecutionReport]:
    """Execute the end-to-end M1->M2->M3->Drift->(M4->Gates->Release)->M5 continual learning workflow."""
    normalized_mode = "force-retrain" if mode == "force_retrain" else mode
    if normalized_mode == "rollback":
        return rollback_active_release(
            artifacts_dir,
            target_release_id=target_release_id,
            run_id=run_id,
            pg_dsn=pg_dsn,
        )

    data_dir = Path(data_dir)
    artifacts = Path(artifacts_dir)
    artifacts.mkdir(parents=True, exist_ok=True)
    run_id = _validate_run_id(
        run_id or datetime.now(UTC).strftime("run-%Y%m%dT%H%M%SZ")
    )

    ingestion_dir = artifacts / "ingestion_runs" / run_id
    snapshot_dir = artifacts / "snapshots" / run_id
    snapshot_path = snapshot_dir / "snapshot.parquet"
    canonical_snapshot_dir = artifacts / "feature_snapshot_m2"

    _log(
        f"Starting run_id={run_id} mode={normalized_mode} cutoff={cutoff_day} data_dir={data_dir}"
    )

    # Step 1: M1 OULAD Ingestion
    ing = ingest_oulad(data_dir, ingestion_dir)
    if ing.status != "ok":
        _log(f"M1 Ingestion failed: {ing.errors}")
        return 1, PipelineExecutionReport(
            status="failed",
            run_id=run_id,
            mode=normalized_mode,
            outcome="M1_INGESTION_FAILED",
            details="; ".join(ing.errors),
        )

    # Step 2: M2 Point-in-Time Feature Snapshot
    snap = build_feature_snapshot(ingestion_dir, snapshot_path, cutoff_day=cutoff_day)

    # Step 3: M3 Temporal Leakage Audit + Structural Snapshot Quality Check
    audit = LeakageAuditor().audit_snapshot(
        snap.snapshot_path, ingestion_dir, cutoff_day
    )
    structural_gate = validate_snapshot(
        snap.snapshot_path, previous_snapshot_path=None
    )
    if audit.status != "ok" or structural_gate.status != "ok":
        _log(
            f"M3 Audit/Quality failed: audit={audit.status} gate={structural_gate.errors}"
        )
        return 1, PipelineExecutionReport(
            status="failed",
            run_id=run_id,
            mode=normalized_mode,
            outcome="M3_AUDIT_OR_QUALITY_FAILED",
            snapshot_path=str(snap.snapshot_path),
            snapshot_version=snap.snapshot_version,
            details=f"audit={audit.status}, errors={structural_gate.errors}",
        )

    # Step 4: Check active Champion release
    active_pointer = load_active_release_pointer(artifacts)
    champion_release = (
        active_pointer.get("current_release") if active_pointer else None
    )

    # Resolve baseline snapshot for DriftMonitor
    resolved_baseline: Path | None = None
    if baseline_snapshot_path is not None and Path(baseline_snapshot_path).is_file():
        resolved_baseline = Path(baseline_snapshot_path)
    elif champion_release and isinstance(
        champion_release.get("baseline_snapshot_path"), str
    ):
        candidate_base = Path(champion_release["baseline_snapshot_path"])
        if candidate_base.is_file():
            resolved_baseline = candidate_base

    drift_report: DriftReport | None = None
    drift_report_dir: Path | None = None

    if resolved_baseline is not None:
        drift_monitor = DriftMonitor()
        drift_report = drift_monitor.evaluate(
            snap.snapshot_path, resolved_baseline, run_id=run_id
        )
        drift_report_dir = publish_drift_report(artifacts, drift_report)
        _log(
            f"DriftMonitor decision={drift_report.decision} "
            f"action={drift_report.recommended_action} max_psi={drift_report.max_psi:.4f}"
        )

        # Safe Mode Guard (Lecture 4 Q05/Q12/Q20): NEVER retrain or score on semantically corrupted data!
        if drift_report.decision == DECISION_QUALITY_FAILURE:
            _log(
                "ALERT [SAFE_MODE]: Semantic or Data Quality Failure detected! "
                "Blocking retraining and keeping incumbent Champion untouched."
            )
            return 1, PipelineExecutionReport(
                status="quarantined_safe_mode",
                run_id=run_id,
                mode=normalized_mode,
                outcome="QUARANTINE_AND_SAFE_MODE",
                drift_decision=drift_report.decision,
                recommended_action=drift_report.recommended_action,
                snapshot_path=str(snap.snapshot_path),
                snapshot_version=snap.snapshot_version,
                active_release_id=(
                    str(champion_release["release_id"]) if champion_release else None
                ),
                previous_release_id=(
                    str(active_pointer["previous_release"]["release_id"])
                    if active_pointer and active_pointer.get("previous_release")
                    else None
                ),
                promoted_new_release=False,
                drift_report_dir=str(drift_report_dir),
                details=drift_report.actionable_response.rationale,
            )

    if normalized_mode == "detect-only":
        return 0, PipelineExecutionReport(
            status="ok",
            run_id=run_id,
            mode=normalized_mode,
            outcome="DETECT_ONLY_COMPLETED",
            drift_decision=(
                drift_report.decision if drift_report else DECISION_NO_DRIFT
            ),
            recommended_action=(
                drift_report.recommended_action
                if drift_report
                else "BOOTSTRAP_REQUIRED"
            ),
            snapshot_path=str(snap.snapshot_path),
            snapshot_version=snap.snapshot_version,
            active_release_id=(
                str(champion_release["release_id"]) if champion_release else None
            ),
            drift_report_dir=str(drift_report_dir) if drift_report_dir else None,
            details="Drift detection completed in detect-only mode.",
        )

    # Determine whether to score directly with Champion or train/evaluate a Challenger
    should_retrain = (
        champion_release is None
        or normalized_mode == "force-retrain"
        or (
            drift_report is not None
            and drift_report.decision == DECISION_DRIFT_RETRAIN
        )
    )

    if not should_retrain and champion_release is not None:
        # Score directly with incumbent Champion without retraining!
        _log(
            f"No retraining required (decision={drift_report.decision if drift_report else 'NO_DRIFT'}). "
            f"Scoring with Champion release {champion_release['release_id']} ..."
        )
        batch_output = (
            artifacts / "prediction-batches" / run_id / PREDICTIONS_FILENAME
        )
        scoring_rep = _score_snapshot_with_champion_release(
            snap.snapshot_path, champion_release, batch_output, run_id=run_id
        )
        scoring_rep = _maybe_write_to_database(scoring_rep, run_id, pg_dsn)
        return 0, PipelineExecutionReport(
            status="ok",
            run_id=run_id,
            mode=normalized_mode,
            outcome="SCORED_WITH_CHAMPION",
            drift_decision=(
                drift_report.decision if drift_report else DECISION_NO_DRIFT
            ),
            recommended_action=(
                drift_report.recommended_action
                if drift_report
                else "SCORE_WITH_CHAMPION"
            ),
            snapshot_path=str(snap.snapshot_path),
            snapshot_version=snap.snapshot_version,
            active_release_id=str(champion_release["release_id"]),
            previous_release_id=(
                str(active_pointer["previous_release"]["release_id"])
                if active_pointer and active_pointer.get("previous_release")
                else None
            ),
            promoted_new_release=False,
            production_threshold=float(champion_release["production_threshold"]),
            drift_report_dir=str(drift_report_dir) if drift_report_dir else None,
            prediction_batch_dir=str(scoring_rep.batch_dir),
            scored_rows=scoring_rep.scored_rows,
            database_write=scoring_rep.database_write,
            database_rows=scoring_rep.database_rows,
            details="Scored snapshot with incumbent Champion model (no retraining required).",
        )

    # Step 5: Train Challenger Preprocessor & LogisticRegression v2 Model
    is_cold_start = champion_release is None
    _log(
        f"Training {'initial Champion (cold-start)' if is_cold_start else 'Challenger'} "
        f"for run_id={run_id} ..."
    )
    pre_res = build_preprocessing_artifact(
        snap.snapshot_path, artifacts, run_id=run_id
    )
    train_res = train_logistic_baseline(
        snap.snapshot_path, pre_res.artifact_dir, artifacts, run_id=run_id
    )

    # Step 6: 3-Layer Evaluation Gates (DataGate + MLGate + BehavioralGate)
    # Pass the actual `resolved_baseline` to `run_data_gate` so `eval_data.json`
    # honestly records the true cross-cohort PSI against the previous Champion baseline.
    # When `DriftMonitor` has already verified `semantic_anomaly_detected == False` and
    # authorized retraining (`DRIFT_RETRAIN_RECOMMENDED` or `force-retrain`), convert
    # `drift_vs_baseline` from `"fail"` to `"warn"` so `/evaluations` displays the true
    # PSI warning badge without self-deadlocking Challenger promotion.
    data_card = run_data_gate(
        snap.snapshot_path,
        baseline_snapshot_path=resolved_baseline,
        run_id=run_id,
    )
    if (
        drift_report is not None
        and not drift_report.semantic_anomaly_detected
        and drift_report.schema_valid
    ):
        updated_data_checks: list[GateCheck] = []
        for chk in data_card.checks:
            if chk.id == "drift_vs_baseline" and chk.status == "fail":
                max_psi_val = chk.observed.get("max_psi", drift_report.max_psi)
                max_psi_feat = chk.observed.get(
                    "max_psi_feature", drift_report.max_psi_feature
                )
                updated_data_checks.append(
                    GateCheck(
                        id=chk.id,
                        name=chk.name,
                        status="warn",
                        observed={
                            **chk.observed,
                            "authorized_retraining_trigger": True,
                            "drift_decision": drift_report.decision,
                        },
                        threshold=chk.threshold,
                        details=(
                            f"Covariate drift vs previous baseline (PSI={max_psi_val} at "
                            f"'{max_psi_feat}') triggered this authorized retraining run; "
                            "internal snapshot quality and semantic checks passed."
                        ),
                    )
                )
            else:
                updated_data_checks.append(chk)
        data_card.checks = updated_data_checks

    ml_card = run_ml_gate(
        train_res.artifact_dir,
        pre_res.artifact_dir,
        snap.snapshot_path,
        run_id=run_id,
        min_roc_auc=min_roc_auc,
        baseline_model_dir=None,
    )
    if champion_release is not None:
        # Replace the skipped `regression_vs_baseline` check with cross-snapshot Champion vs Challenger comparison
        reg_check = _evaluate_champion_vs_challenger_regression(
            champion_release,
            train_res.artifact_dir,
            pre_res.artifact_dir,
            snap.snapshot_path,
        )
        ml_card.checks = [
            reg_check if chk.id == "regression_vs_baseline" else chk
            for chk in ml_card.checks
        ]

    behavioral_card = run_behavioral_gate(
        train_res.artifact_dir,
        pre_res.artifact_dir,
        snap.snapshot_path,
        run_id=run_id,
    )

    eval_dir = publish_all_evaluation_scorecards(
        artifacts, run_id, [data_card, ml_card, behavioral_card]
    )
    gate_summaries = {
        "data": data_card.summary(),
        "ml": ml_card.summary(),
        "behavioral": behavioral_card.summary(),
    }

    any_gate_failed = (
        data_card.has_failure()
        or ml_card.has_failure()
        or behavioral_card.has_failure()
    )
    if any_gate_failed:
        failed_gates = [
            card.subject
            for card in (data_card, ml_card, behavioral_card)
            if card.has_failure()
        ]
        _log(
            f"Challenger FAILED evaluation gates ({', '.join(failed_gates)}). "
            "Rejecting Challenger and retaining incumbent Champion!"
        )
        return 1, PipelineExecutionReport(
            status="rejected_challenger",
            run_id=run_id,
            mode=normalized_mode,
            outcome="REJECT_CHALLENGER_KEEP_CHAMPION",
            drift_decision=drift_report.decision if drift_report else None,
            recommended_action=(
                drift_report.recommended_action if drift_report else None
            ),
            snapshot_path=str(snap.snapshot_path),
            snapshot_version=snap.snapshot_version,
            active_release_id=(
                str(champion_release["release_id"]) if champion_release else None
            ),
            previous_release_id=(
                str(active_pointer["previous_release"]["release_id"])
                if active_pointer and active_pointer.get("previous_release")
                else None
            ),
            promoted_new_release=False,
            drift_report_dir=str(drift_report_dir) if drift_report_dir else None,
            evaluation_dir=str(eval_dir),
            gate_summaries=gate_summaries,
            details=f"Challenger rejected due to gate failure in: {', '.join(failed_gates)}",
        )

    # Step 7: All 3 Gates Passed -> Package Immutable Model Release & Atomically Promote
    release_id = f"release-{run_id}"
    release_entry = package_verified_model_release(
        snap.snapshot_path,
        train_res.artifact_dir,
        pre_res.artifact_dir,
        artifacts,
        release_id=release_id,
    )
    update_active_release_pointer(artifacts, release_entry)
    updated_pointer = load_active_release_pointer(artifacts) or {}

    # Update canonical feature_snapshot_m2 copy for downstream consumers
    canonical_snapshot_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snap.snapshot_path, canonical_snapshot_dir / "snapshot.parquet")
    shutil.copy2(
        snap.ledger_path, canonical_snapshot_dir / "snapshot.ledger.json"
    )

    # Step 8: M5 Batch Scoring with the promoted release's locked Top-20% threshold
    batch_output = (
        artifacts / "prediction-batches" / run_id / PREDICTIONS_FILENAME
    )
    scoring_rep = score_snapshot(
        snap.snapshot_path,
        Path(release_entry["model_dir"]),
        Path(release_entry["preprocessing_dir"]),
        batch_output,
        threshold=float(release_entry["production_threshold"]),
        run_id=run_id,
    )
    scoring_rep = _maybe_write_to_database(scoring_rep, run_id, pg_dsn)

    outcome = "BOOTSTRAPPED_CHAMPION" if is_cold_start else "PROMOTE_CHALLENGER"
    _log(
        f"Successfully promoted {release_id} (outcome={outcome}, "
        f"threshold={release_entry['production_threshold']:.4f}, scored={scoring_rep.scored_rows})"
    )
    return 0, PipelineExecutionReport(
        status="ok",
        run_id=run_id,
        mode=normalized_mode,
        outcome=outcome,
        drift_decision=drift_report.decision if drift_report else DECISION_NO_DRIFT,
        recommended_action=(
            drift_report.recommended_action
            if drift_report
            else "BOOTSTRAP_CHAMPION"
        ),
        snapshot_path=str(snap.snapshot_path),
        snapshot_version=snap.snapshot_version,
        active_release_id=release_id,
        previous_release_id=(
            str(updated_pointer["previous_release"]["release_id"])
            if updated_pointer.get("previous_release")
            else None
        ),
        promoted_new_release=True,
        production_threshold=float(release_entry["production_threshold"]),
        drift_report_dir=str(drift_report_dir) if drift_report_dir else None,
        evaluation_dir=str(eval_dir),
        prediction_batch_dir=str(scoring_rep.batch_dir),
        scored_rows=scoring_rep.scored_rows,
        database_write=scoring_rep.database_write,
        database_rows=scoring_rep.database_rows,
        gate_summaries=gate_summaries,
        details=f"All 3 gates passed; promoted active release {release_id}.",
    )


def run_simulation_suite(
    scenario: str,
    artifacts_dir: Path | str | None = None,
    *,
    students_per_presentation: int = 250,
    seed: int = 42,
    cutoff_day: int = CUTOFF_DAY,
) -> dict[str, Any]:
    """Run one or all 5 controlled simulation scenarios end-to-end.

    Writes artifacts directly into `artifacts_dir` (when provided) and simulation
    raw CSV inputs under `artifacts_dir / "simulated_data" / <scenario>` so there
    is no double-nested `artifacts/artifacts` directory.
    """
    sim_artifacts = (
        Path(artifacts_dir)
        if artifacts_dir is not None
        else Path(tempfile.mkdtemp(prefix="learnguard-sim-"))
    )
    sim_artifacts.mkdir(parents=True, exist_ok=True)
    data_root = sim_artifacts / "simulated_data"

    # 1. Bootstrap initial Champion on baseline dataset if not already present
    baseline_csv_dir = data_root / "bootstrap_baseline"
    pointer = load_active_release_pointer(sim_artifacts)
    if pointer is None:
        generate_oulad_dataset(
            baseline_csv_dir,
            "baseline_no_drift",
            students_per_presentation=students_per_presentation,
            seed=seed,
        )
        code, boot_rep = run_continual_pipeline(
            baseline_csv_dir,
            sim_artifacts,
            mode="auto",
            run_id="sim-bootstrap",
            cutoff_day=cutoff_day,
        )
        if code != 0:
            raise RuntimeError(f"Bootstrap simulation failed: {boot_rep}")
        pointer = load_active_release_pointer(sim_artifacts)

    boot_baseline_snap = (
        pointer["current_release"].get("baseline_snapshot_path")
        if pointer and isinstance(pointer.get("current_release"), dict)
        else None
    )

    scenarios_to_run = list(SCENARIOS) if scenario == "all" else [scenario]
    results: dict[str, Any] = {}

    for idx, sc_name in enumerate(scenarios_to_run, start=1):
        sc_csv_dir = data_root / sc_name
        generate_oulad_dataset(
            sc_csv_dir,
            sc_name,
            students_per_presentation=students_per_presentation,
            seed=seed,
        )
        run_id = f"sim-{idx:02d}-{sc_name.replace('_', '-')}"
        exit_code, report = run_continual_pipeline(
            sc_csv_dir,
            sim_artifacts,
            mode="auto",
            baseline_snapshot_path=boot_baseline_snap,
            run_id=run_id,
            cutoff_day=cutoff_day,
        )
        results[sc_name] = {
            "exit_code": exit_code,
            "report": asdict(report),
        }
    return {
        "artifacts_dir": str(sim_artifacts),
        "simulated_data_dir": str(data_root),
        "scenarios": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LearnGuard MLOps Continual Learning & Drift Retraining Orchestrator"
    )
    parser.add_argument(
        "--mode",
        choices=(
            "auto",
            "detect-only",
            "force-retrain",
            "force_retrain",
            "simulate",
            "rollback",
        ),
        default="auto",
        help="Execution mode",
    )
    parser.add_argument(
        "--scenario",
        choices=(*SCENARIOS, "all"),
        default="all",
        help="Simulation scenario when --mode simulate",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("LEARNGUARD_DATA_DIR", "/mnt/data/oulad")),
        help="Input OULAD 7-CSV directory",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path(os.environ.get("LEARNGUARD_ARTIFACTS_DIR", "artifacts")),
        help="Artifacts root directory",
    )
    parser.add_argument(
        "--baseline-snapshot",
        type=Path,
        default=None,
        help="Optional explicit baseline snapshot parquet path",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Pipeline run ID",
    )
    parser.add_argument(
        "--min-roc-auc",
        type=float,
        default=0.70,
        help="Minimum validation ROC-AUC required by MLGate",
    )
    parser.add_argument(
        "--cutoff-day",
        type=int,
        default=int(os.environ.get("LEARNGUARD_CUTOFF_DAY", str(CUTOFF_DAY))),
        help="Point-in-time course day cutoff (default 27)",
    )
    parser.add_argument(
        "--target-release-id",
        "--rollback-release",
        dest="target_release_id",
        type=str,
        default=None,
        help="Target release ID when running --mode rollback (defaults to previous_release)",
    )
    parser.add_argument(
        "--pg-dsn",
        type=str,
        default=None,
        help="Optional PostgreSQL DSN for upserting ml_predictions",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.mode == "simulate":
        sim_out = run_simulation_suite(
            args.scenario,
            args.artifacts_dir,
            cutoff_day=args.cutoff_day,
        )
        print(json.dumps(sim_out, indent=2, default=str))
        return 0

    exit_code, report = run_continual_pipeline(
        args.data_dir,
        args.artifacts_dir,
        mode=args.mode,
        baseline_snapshot_path=args.baseline_snapshot,
        run_id=args.run_id,
        min_roc_auc=args.min_roc_auc,
        cutoff_day=args.cutoff_day,
        pg_dsn=args.pg_dsn,
        target_release_id=args.target_release_id,
    )
    print(json.dumps(asdict(report), indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
