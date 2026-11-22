#!/usr/bin/env python3
"""Gate 3 — Behavioral Model Testing (`eval-report.v1`, subject="behavioral").

Implements CMU MLIP Lecture 5 (Model Quality & Behavioral Testing) and Lecture 6
(System-Level Testing & Safeguards):
  1. `mft_canonical_profiles` (Minimum Functionality Test):
     Constructs canonical high-engagement/high-score students vs disengaged/zero-submission
     students across validation modules; verifies high-risk students receive significantly
     higher predicted risk scores (`mean_risk_disengaged > mean_risk_engaged + 0.25` and
     100% pairwise ordering).
  2. `invariance_row_permutation` (Metamorphic / Invariance Test):
     Permutes row order of the validation DataFrame before preprocessing & inference and
     verifies matched predictions are invariant within `1e-12`.
  3. `invariance_pseudonymous_key` (Cross-Boundary Contract Invariance):
     Verifies `_pseudonymous_key` matches canonical test vectors (`AAA/2013B/1` ->
     `4c337e13fc7b6871`, `AAA/2013J/11391` -> `7bd60aced1ccab8c`).
  4. `directional_clicks_monotonicity` (Directional Expectation Test):
     Reduces `n_clicks_before_cutoff` (and scales `click_trend_w3_w4`) by 50% ceteris
     paribus on active validation students and verifies mean risk does not decrease and
     individual directional compliance >= 95%.
  5. `directional_score_monotonicity` (Directional Expectation Test):
     Reduces `avg_score_submitted` by 25 points (clipped to 0) ceteris paribus on
     validation students with prior submissions and verifies mean risk increases/stays
     non-decreasing and individual compliance >= 95%.
  6. `abstention_and_uncertainty_routing` (Safeguard & Abstention Test):
     Verifies `BatchScorer.assign_review_state` routes 100% of `insufficient_data` cases
     to `PredictionStatus.INSUFFICIENT_DATA` (`predicted_label = None`) and 100% of
     sufficient-data cases with `uncertainty >= 0.80` to `PredictionStatus.MANUAL_REVIEW`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from learnguard.data.loading import load_snapshot_partitions
from learnguard.evaluation.scorecard import (
    CHECK_STATUSES,
    EVAL_SCHEMA_VERSION,
    EVALUATIONS_DIRNAME,
    MANIFEST_FILENAME,
    SCORECARD_FILENAME,
    SUCCESS_FILENAME,
    GateCheck,
    Scorecard,
    _jsonable,
)
from learnguard.ml.model_interface import ScoringModel, load_scoring_model
from learnguard.ml.preprocessing import _file_hash, _prepare_split, _validate_run_id
from learnguard.ml.scoring import (
    HIGH_UNCERTAINTY_THRESHOLD,
    BatchScorer,
    PredictionStatus,
    _pseudonymous_key,
)

BEHAVIORAL_SUBJECT = "behavioral"
BEHAVIORAL_SCORECARD_FILENAME = "eval_behavioral.json"
MFT_MIN_RISK_GAP = 0.25

CANONICAL_KEY_VECTORS: tuple[tuple[str, str, int, str], ...] = (
    ("AAA", "2013B", 1, "4c337e13fc7b6871"),
    ("AAA", "2013J", 11391, "7bd60aced1ccab8c"),
)


@dataclass
class BehavioralScorecard:
    """`eval-report.v1` compatible scorecard for `subject="behavioral"`."""

    run_id: str
    subject: str = BEHAVIORAL_SUBJECT
    checks: list[GateCheck] = field(default_factory=list)
    inputs: dict[str, str | None] = field(default_factory=dict)
    schema_version: str = EVAL_SCHEMA_VERSION
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def add(self, check: GateCheck) -> GateCheck:
        self.checks.append(check)
        return check

    def summary(self) -> dict[str, int]:
        counts = {status: 0 for status in CHECK_STATUSES}
        for check in self.checks:
            counts[check.status] += 1
        return {"total": len(self.checks), **counts}

    def has_failure(self) -> bool:
        return any(check.status == "fail" for check in self.checks)

    def worst_status(self) -> str:
        if self.has_failure():
            return "fail"
        if any(check.status == "warn" for check in self.checks):
            return "warn"
        return "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "subject": self.subject,
            "created_at": self.created_at,
            "inputs": dict(self.inputs),
            "checks": [
                {
                    "id": check.id,
                    "name": check.name,
                    "status": check.status,
                    "threshold": check.threshold,
                    "observed": _jsonable(check.observed),
                    "details": check.details,
                }
                for check in self.checks
            ],
            "summary": self.summary(),
        }


def run_behavioral_gate(
    model_artifact_dir: Path | str,
    preprocessing_artifact_dir: Path | str,
    snapshot_path: Path | str,
    run_id: str,
) -> BehavioralScorecard:
    """Execute all 6 Lecture 5 Behavioral Model Tests on the validation split."""
    run_id = _validate_run_id(run_id)
    model_dir = Path(model_artifact_dir)
    pre_dir = Path(preprocessing_artifact_dir)
    snap_path = Path(snapshot_path)

    card = BehavioralScorecard(
        run_id=run_id,
        inputs={
            "snapshot": str(snap_path),
            "model": str(model_dir),
            "preprocessing": str(pre_dir),
        },
    )

    model = load_scoring_model(model_dir, snap_path, pre_dir)
    selected = load_snapshot_partitions(snap_path, ("validation",))
    prepared = _prepare_split("validation", selected.frame("validation"))

    card.add(_check_mft_canonical_profiles(model, prepared.X))
    card.add(_check_invariance_row_permutation(model, prepared.keys, prepared.X))
    card.add(_check_invariance_pseudonymous_key())
    card.add(_check_directional_clicks_monotonicity(model, prepared.X))
    card.add(_check_directional_score_monotonicity(model, prepared.X))
    card.add(_check_abstention_and_uncertainty_routing())
    return card


def _check_mft_canonical_profiles(
    model: ScoringModel, val_X: pd.DataFrame
) -> GateCheck:
    """1. Minimum Functionality Test (MFT): high-engagement vs disengaged profiles."""
    clicks_p90 = float(max(np.quantile(val_X["n_clicks_before_cutoff"], 0.90), 250.0))
    clicks_p10 = float(min(np.quantile(val_X["n_clicks_before_cutoff"], 0.10), 15.0))
    sub_max = float(max(np.quantile(val_X["n_submitted_before_cutoff"], 0.90), 3.0))

    # Build paired canonical templates across distinct module_presentations in validation
    presentations = sorted(val_X["module_presentation"].astype(str).unique())[:6]
    base_template = val_X.iloc[0].to_dict()

    engaged_rows: list[dict[str, Any]] = []
    disengaged_rows: list[dict[str, Any]] = []
    for mp in presentations:
        eng = dict(base_template)
        eng.update({
            "module_presentation": mp,
            "n_clicks_before_cutoff": clicks_p90,
            "click_trend_w3_w4": max(clicks_p90 * 0.25, 40.0),
            "n_submitted_before_cutoff": sub_max,
            "avg_score_submitted": 90.0,
            "num_of_prev_attempts": 0,
            "insufficient_data": False,
        })
        engaged_rows.append(eng)

        dis = dict(base_template)
        dis.update({
            "module_presentation": mp,
            "n_clicks_before_cutoff": clicks_p10,
            "click_trend_w3_w4": -max(clicks_p10, 20.0),
            "n_submitted_before_cutoff": 0.0,
            "avg_score_submitted": np.nan,
            "num_of_prev_attempts": 1,
            "insufficient_data": False,
        })
        disengaged_rows.append(dis)

    df_engaged = pd.DataFrame(engaged_rows)[list(val_X.columns)]
    df_disengaged = pd.DataFrame(disengaged_rows)[list(val_X.columns)]

    scores_engaged = np.asarray(model.predict_positive_proba(df_engaged), dtype=np.float64)
    scores_disengaged = np.asarray(
        model.predict_positive_proba(df_disengaged), dtype=np.float64
    )

    mean_eng = float(scores_engaged.mean())
    mean_dis = float(scores_disengaged.mean())
    gap = mean_dis - mean_eng
    pairwise_rate = float(np.mean(scores_disengaged > scores_engaged))

    observed = {
        "profile_pairs": len(presentations),
        "mean_risk_engaged": round(mean_eng, 4),
        "mean_risk_disengaged": round(mean_dis, 4),
        "risk_gap": round(gap, 4),
        "pairwise_ordering_accuracy": round(pairwise_rate, 4),
    }
    threshold = (
        f"mean_risk_disengaged - mean_risk_engaged >= {MFT_MIN_RISK_GAP} "
        "and pairwise_ordering == 1.0"
    )
    if gap >= MFT_MIN_RISK_GAP and pairwise_rate == 1.0:
        return GateCheck(
            id="mft_canonical_profiles",
            name="MFT: Canonical disengaged vs high-engagement student profiles",
            status="pass",
            observed=observed,
            threshold=threshold,
            details=(
                f"MFT passed: disengaged mean risk={mean_dis:.3f} vs engaged={mean_eng:.3f} "
                f"(gap={gap:+.3f}, pairwise=100%)"
            ),
        )
    return GateCheck(
        id="mft_canonical_profiles",
        name="MFT: Canonical disengaged vs high-engagement student profiles",
        status="fail",
        observed=observed,
        threshold=threshold,
        details=(
            f"MFT failed: disengaged mean risk={mean_dis:.3f} vs engaged={mean_eng:.3f} "
            f"(gap={gap:+.3f}, pairwise={pairwise_rate:.1%})"
        ),
    )


def _check_invariance_row_permutation(
    model: ScoringModel, val_keys: pd.DataFrame, val_X: pd.DataFrame
) -> GateCheck:
    """2. Invariance Test (INV): row permutation produces identical risk scores."""
    orig_scores = np.asarray(model.predict_positive_proba(val_X), dtype=np.float64)
    rng = np.random.default_rng(42)
    perm_idx = rng.permutation(len(val_X))
    inverse_idx = np.argsort(perm_idx)

    perm_X = val_X.iloc[perm_idx].reset_index(drop=True)
    perm_scores = np.asarray(model.predict_positive_proba(perm_X), dtype=np.float64)
    restored_scores = perm_scores[inverse_idx]

    max_diff = float(np.max(np.abs(orig_scores - restored_scores))) if len(orig_scores) else 0.0
    observed = {
        "rows_tested": len(val_X),
        "max_abs_diff": max_diff,
    }
    threshold = "max_abs_diff <= 1e-12"
    if max_diff <= 1e-12:
        return GateCheck(
            id="invariance_row_permutation",
            name="INV: Row-order permutation invariance of predicted risk scores",
            status="pass",
            observed=observed,
            threshold=threshold,
            details=f"Permutation invariance verified across {len(val_X)} rows (max_diff={max_diff:.3e})",
        )
    return GateCheck(
        id="invariance_row_permutation",
        name="INV: Row-order permutation invariance of predicted risk scores",
        status="fail",
        observed=observed,
        threshold=threshold,
        details=f"Permutation invariance violated: max_diff={max_diff:.3e} > 1e-12",
    )


def _check_invariance_pseudonymous_key() -> GateCheck:
    """3. Contract Invariance Test (INV): pseudonymous student_key test vectors."""
    results: list[dict[str, Any]] = []
    all_match = True
    for mod, pres, sid, expected in CANONICAL_KEY_VECTORS:
        actual = _pseudonymous_key(mod, pres, sid)
        matched = actual == expected
        all_match = all_match and matched
        results.append({
            "input": f"{mod}/{pres}/{sid}",
            "expected": expected,
            "actual": actual,
            "matched": matched,
        })
    observed = {"vectors_checked": len(results), "results": results}
    threshold = "100% match with DB_CONTRACT.md student_key test vectors"
    if all_match:
        return GateCheck(
            id="invariance_pseudonymous_key",
            name="INV: Pseudonymous student_key hash contract vectors",
            status="pass",
            observed=observed,
            threshold=threshold,
            details="All canonical student_key SHA-256 test vectors matched 100%",
        )
    return GateCheck(
        id="invariance_pseudonymous_key",
        name="INV: Pseudonymous student_key hash contract vectors",
        status="fail",
        observed=observed,
        threshold=threshold,
        details="Pseudonymous student_key mismatch detected against DB_CONTRACT.md vectors",
    )


def _check_directional_clicks_monotonicity(
    model: ScoringModel, val_X: pd.DataFrame
) -> GateCheck:
    """4. Directional Expectation Test (DIR): 50% reduction in VLE clicks ceteris paribus."""
    active_mask = val_X["n_clicks_before_cutoff"] > 10
    sample_X = val_X.loc[active_mask].copy() if active_mask.any() else val_X.copy()

    base_scores = np.asarray(model.predict_positive_proba(sample_X), dtype=np.float64)
    perturbed_X = sample_X.copy()
    perturbed_X["n_clicks_before_cutoff"] = np.floor(
        perturbed_X["n_clicks_before_cutoff"] * 0.5
    )
    # Also shift week 3-4 click trend negatively when activity drops in half
    perturbed_X["click_trend_w3_w4"] = (
        perturbed_X["click_trend_w3_w4"]
        - 0.25 * sample_X["n_clicks_before_cutoff"]
    )

    perturbed_scores = np.asarray(
        model.predict_positive_proba(perturbed_X), dtype=np.float64
    )
    deltas = perturbed_scores - base_scores
    mean_delta = float(deltas.mean()) if len(deltas) else 0.0
    compliance_rate = float(np.mean(deltas >= -1e-9)) if len(deltas) else 1.0

    observed = {
        "active_rows_tested": len(sample_X),
        "mean_risk_before": round(float(base_scores.mean()), 4),
        "mean_risk_after_50pct_click_drop": round(float(perturbed_scores.mean()), 4),
        "mean_risk_delta": round(mean_delta, 6),
        "individual_compliance_rate": round(compliance_rate, 4),
    }
    threshold = "mean_risk_delta >= -1e-9 and individual_compliance_rate >= 0.95"
    if mean_delta >= -1e-9 and compliance_rate >= 0.95:
        return GateCheck(
            id="directional_clicks_monotonicity",
            name="DIR: Reducing VLE clicks by 50% ceteris paribus does not decrease risk",
            status="pass",
            observed=observed,
            threshold=threshold,
            details=(
                f"Click directional monotonicity passed: mean_delta={mean_delta:+.4f}, "
                f"compliance={compliance_rate:.1%} across {len(sample_X)} active rows"
            ),
        )
    return GateCheck(
        id="directional_clicks_monotonicity",
        name="DIR: Reducing VLE clicks by 50% ceteris paribus does not decrease risk",
        status="fail",
        observed=observed,
        threshold=threshold,
        details=(
            f"Click directional monotonicity failed: mean_delta={mean_delta:+.4f}, "
            f"compliance={compliance_rate:.1%}"
        ),
    )


def _check_directional_score_monotonicity(
    model: ScoringModel, val_X: pd.DataFrame
) -> GateCheck:
    """5. Directional Expectation Test (DIR): -25 points on avg_score_submitted ceteris paribus."""
    has_score_mask = val_X["avg_score_submitted"].notna() & (val_X["avg_score_submitted"] > 10.0)
    sample_X = val_X.loc[has_score_mask].copy() if has_score_mask.any() else val_X.copy()

    base_scores = np.asarray(model.predict_positive_proba(sample_X), dtype=np.float64)
    perturbed_X = sample_X.copy()
    perturbed_X["avg_score_submitted"] = np.clip(
        perturbed_X["avg_score_submitted"].fillna(50.0) - 25.0, 0.0, 100.0
    )

    perturbed_scores = np.asarray(
        model.predict_positive_proba(perturbed_X), dtype=np.float64
    )
    deltas = perturbed_scores - base_scores
    mean_delta = float(deltas.mean()) if len(deltas) else 0.0
    compliance_rate = float(np.mean(deltas >= -1e-9)) if len(deltas) else 1.0

    observed = {
        "scored_rows_tested": len(sample_X),
        "mean_risk_before": round(float(base_scores.mean()), 4),
        "mean_risk_after_25pt_score_drop": round(float(perturbed_scores.mean()), 4),
        "mean_risk_delta": round(mean_delta, 6),
        "individual_compliance_rate": round(compliance_rate, 4),
    }
    threshold = "mean_risk_delta >= -1e-9 and individual_compliance_rate >= 0.95"
    if mean_delta >= -1e-9 and compliance_rate >= 0.95:
        return GateCheck(
            id="directional_score_monotonicity",
            name="DIR: Reducing avg_score_submitted by 25 points increases at-risk probability",
            status="pass",
            observed=observed,
            threshold=threshold,
            details=(
                f"Score directional monotonicity passed: mean_delta={mean_delta:+.4f}, "
                f"compliance={compliance_rate:.1%} across {len(sample_X)} scored rows"
            ),
        )
    return GateCheck(
        id="directional_score_monotonicity",
        name="DIR: Reducing avg_score_submitted by 25 points increases at-risk probability",
        status="fail",
        observed=observed,
        threshold=threshold,
        details=(
            f"Score directional monotonicity failed: mean_delta={mean_delta:+.4f}, "
            f"compliance={compliance_rate:.1%}"
        ),
    )


def _check_abstention_and_uncertainty_routing() -> GateCheck:
    """6. Safeguard & Abstention Test (Lec 1/5/6): insufficient_data and uncertainty >= 0.80."""
    scorer = BatchScorer()
    threshold_val = 0.50

    # Test grid of (risk_score, data_status, expected_status, expected_label_is_none)
    cases = [
        (0.10, "insufficient_data", PredictionStatus.INSUFFICIENT_DATA, True),
        (0.50, "insufficient_data", PredictionStatus.INSUFFICIENT_DATA, True),
        (0.95, "insufficient_data", PredictionStatus.INSUFFICIENT_DATA, True),
        (0.50, "ok", PredictionStatus.MANUAL_REVIEW, False),   # uncertainty = 1.00 >= 0.80
        (0.45, "ok", PredictionStatus.MANUAL_REVIEW, False),   # uncertainty = 0.90 >= 0.80
        (0.55, "ok", PredictionStatus.MANUAL_REVIEW, False),   # uncertainty = 0.90 >= 0.80
        (0.10, "ok", PredictionStatus.SCORED, False),          # uncertainty = 0.20 < 0.80
        (0.88, "ok", PredictionStatus.SCORED, False),          # uncertainty = 0.24 < 0.80
    ]

    failures: list[str] = []
    for risk_score, data_status, expected_status, expect_none_label in cases:
        uncertainty = 1.0 - abs(2.0 * risk_score - 1.0)
        actual_status = scorer.assign_review_state(
            risk_score, threshold_val, uncertainty, data_status
        )
        predicted_label = (
            None
            if actual_status is PredictionStatus.INSUFFICIENT_DATA
            else int(risk_score >= threshold_val)
        )
        if actual_status != expected_status:
            failures.append(
                f"risk={risk_score},data={data_status}:got={actual_status.value},expected={expected_status.value}"
            )
        if expect_none_label and predicted_label is not None:
            failures.append(f"risk={risk_score},data={data_status}:predicted_label_not_null")

    observed = {
        "cases_tested": len(cases),
        "high_uncertainty_threshold": HIGH_UNCERTAINTY_THRESHOLD,
        "failures": failures,
    }
    threshold = "100% insufficient_data -> INSUFFICIENT_DATA (label=None); 100% uncertainty>=0.80 -> MANUAL_REVIEW"
    if not failures:
        return GateCheck(
            id="abstention_and_uncertainty_routing",
            name="SAFEGUARD: Abstention (insufficient_data) and Uncertainty (manual_review) routing",
            status="pass",
            observed=observed,
            threshold=threshold,
            details=(
                f"All {len(cases)} abstention & uncertainty safeguard routing cases "
                "verified 100%"
            ),
        )
    return GateCheck(
        id="abstention_and_uncertainty_routing",
        name="SAFEGUARD: Abstention (insufficient_data) and Uncertainty (manual_review) routing",
        status="fail",
        observed=observed,
        threshold=threshold,
        details=f"Abstention/uncertainty routing failed: {'; '.join(failures)}",
    )


def publish_all_evaluation_scorecards(
    artifacts_dir: Path | str,
    run_id: str,
    scorecards: list[Scorecard | BehavioralScorecard],
) -> Path:
    """Atomically publish Data, ML, and Behavioral `eval-report.v1` scorecards into `evaluations/<run-id>/`.

    Fully compatible with `BE-MLOPS/src/learnguard_backend/api/app.py` (`_scan_runs` and
    `get_evaluation`), which dynamically scans `eval_*.json` and reads `manifest.json`.
    """
    run_id = _validate_run_id(run_id)
    if not scorecards:
        raise ValueError("evaluation_scorecards_empty")
    subjects = [card.subject for card in scorecards]
    if len(set(subjects)) != len(subjects):
        raise ValueError(f"evaluation_duplicate_subject:{','.join(subjects)}")

    filename_map = {
        **SCORECARD_FILENAME,
        BEHAVIORAL_SUBJECT: BEHAVIORAL_SCORECARD_FILENAME,
    }

    root = Path(artifacts_dir) / EVALUATIONS_DIRNAME
    target = root / run_id
    if target.exists():
        raise FileExistsError(f"evaluation_run_id_exists:{run_id}")
    root.mkdir(parents=True, exist_ok=True)
    staging = root / f".{run_id}.staging-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        files: dict[str, str] = {}
        for card in scorecards:
            fname = filename_map.get(card.subject, f"eval_{card.subject}.json")
            path = staging / fname
            path.write_text(
                json.dumps(card.to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            files[path.name] = _file_hash(path)

        manifest = {
            "schema_version": EVAL_SCHEMA_VERSION,
            "run_id": run_id,
            "subjects": subjects,
            "scorecards": files,
            "created_at": datetime.now(UTC).isoformat(),
        }
        manifest_path = staging / MANIFEST_FILENAME
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        worst = max(
            (card.worst_status() for card in scorecards),
            key=lambda s: ("pass", "warn", "fail").index(s),
        )
        (staging / SUCCESS_FILENAME).write_text(
            json.dumps(
                {
                    "schema_version": EVAL_SCHEMA_VERSION,
                    "run_id": run_id,
                    "status": worst,
                    "manifest_sha256": _file_hash(manifest_path),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if target.exists():
            raise FileExistsError(f"evaluation_run_id_exists:{run_id}")
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LearnGuard MLOps Lecture 5 Behavioral Model Testing Gate"
    )
    parser.add_argument("--model-dir", required=True, type=Path, help="Model artifact dir")
    parser.add_argument(
        "--preprocessing-dir", required=True, type=Path, help="Preprocessing artifact dir"
    )
    parser.add_argument("--snapshot", required=True, type=Path, help="Snapshot parquet path")
    parser.add_argument(
        "--artifacts-dir", type=Path, default=Path("artifacts"), help="Artifacts directory"
    )
    parser.add_argument("--run-id", type=str, default=None, help="Evaluation run ID")
    args = parser.parse_args(argv)

    run_id = args.run_id or datetime.now(UTC).strftime("behavioral-%Y%m%dT%H%M%SZ")
    card = run_behavioral_gate(
        args.model_dir, args.preprocessing_dir, args.snapshot, run_id=run_id
    )
    out_dir = publish_all_evaluation_scorecards(args.artifacts_dir, run_id, [card])
    print(json.dumps(card.to_dict(), indent=2))
    print(f"[behavioral-gate] published to {out_dir}", flush=True)
    return 1 if card.has_failure() else 0


if __name__ == "__main__":
    raise SystemExit(main())
