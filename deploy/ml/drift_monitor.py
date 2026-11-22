#!/usr/bin/env python3
"""Multi-layer Data Drift & Semantic Anomaly Triage Engine (`drift-report.v1`).

Implements CMU MLIP Lecture 4 (Data Quality Engineering, Q05, Q12, Q19-Q22):
  1. Schema & Semantic Integrity Guard:
     - Verifies all 21 `EXPECTED_COLUMNS`, `label` domain (`{0, 1}` when present;
       detects `ground_truth_available = False` when `label` contains NaN due to
       delayed ground truth `ASM-03`), `split` in VALID_SPLITS, unique composite
       primary keys `KEYS`, physical domain invariants (`avg_score_submitted` in
       [0, 100], non-negative click/submission counts).
     - Semantic Scale Anomaly Detection (Lec 4 Q05/Q12): detects LMS unit/extractor
       bugs where median or P95 of `n_clicks_before_cutoff` or `n_submitted_before_cutoff`
       jumps > 10.0x or drops < 0.05x relative to baseline, or any original feature
       null rate exceeds 0.60.
  2. Volume & Missingness Stability Check:
     - `volume_ratio = len(current) / len(baseline)` within [0.10, 10.0].
     - Feature-level null rate delta `null_delta_by_feature`.
  3. Covariate Shift Metrics (PSI + Two-Sample KS Test):
     - Evaluated across validation split when both splits have >= `min_sample_size`
       (default `MIN_PSI_SAMPLE = 200`), with fallback to full snapshot cohort when
       smaller synthetic fixtures are tested.
     - Numeric features: `_psi_numeric` + `scipy.stats.ks_2samp` (`ks_stat`, `ks_pvalue`).
     - Categorical features: `_psi_categorical`.
  4. Label-Prior & Insufficient-Data Shift:
     - Absolute delta in `label` mean (when `ground_truth_available=True`) and
       `insufficient_data` fraction.
  5. Slice-Level Drift Diagnosis (Lec 4 Q21):
     - Computes per-`code_module` max feature PSI to distinguish `localized_slice_shift`
       from `global_cohort_shift`.
  6. Triage Decision Engine & Actionable Alert-to-Response Statement (Lec 4 Q20 & Q22):
     - `DATA_QUALITY_OR_SEMANTIC_FAILURE` -> `QUARANTINE_AND_SAFE_MODE` (NEVER retrain!)
     - `DRIFT_RETRAIN_RECOMMENDED` (when `ground_truth_available=True`) -> `TRIGGER_RETRAINING`
     - `WARN_MONITOR` (when drift detected but `ground_truth_available=False` per `ASM-03`)
       -> `SCORE_WITH_CHAMPION_AWAIT_LABELS`
     - `WARN_MONITOR` (moderate drift `0.10 < max_psi <= 0.20`) -> `SCORE_WITH_CHAMPION_AND_MONITOR`
     - `NO_DRIFT` -> `SCORE_WITH_CHAMPION`
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from learnguard.data.features import KEYS
from learnguard.data.quality import (
    CATEGORICAL_FEATURES,
    EXPECTED_COLUMNS,
    MIN_PSI_SAMPLE,
    NUMERIC_FEATURES,
    VALID_SPLITS,
    _psi_categorical,
    _psi_numeric,
)
from learnguard.evaluation.data_gate import ORIGINAL_FEATURES
from learnguard.ml.preprocessing import _file_hash, _validate_run_id
from scipy.stats import ks_2samp

DRIFT_REPORT_SCHEMA_VERSION = "drift-report.v1"
DRIFT_REPORTS_DIRNAME = "drift-reports"

DECISION_NO_DRIFT = "NO_DRIFT"
DECISION_WARN_MONITOR = "WARN_MONITOR"
DECISION_DRIFT_RETRAIN = "DRIFT_RETRAIN_RECOMMENDED"
DECISION_QUALITY_FAILURE = "DATA_QUALITY_OR_SEMANTIC_FAILURE"

ACTION_SCORE_CHAMPION = "SCORE_WITH_CHAMPION"
ACTION_SCORE_AND_MONITOR = "SCORE_WITH_CHAMPION_AND_MONITOR"
ACTION_SCORE_AWAIT_LABELS = "SCORE_WITH_CHAMPION_AWAIT_LABELS"
ACTION_TRIGGER_RETRAINING = "TRIGGER_RETRAINING"
ACTION_QUARANTINE_SAFE_MODE = "QUARANTINE_AND_SAFE_MODE"


@dataclass(frozen=True)
class DriftThresholds:
    """Configurable thresholds for multi-layer drift triage (aligned with spec v1.0)."""

    psi_warn_threshold: float = 0.10
    psi_fail_threshold: float = 0.20
    ks_stat_threshold: float = 0.15
    ks_pvalue_threshold: float = 0.01
    label_rate_delta_threshold: float = 0.15
    max_null_fraction: float = 0.60
    min_volume_ratio: float = 0.10
    max_volume_ratio: float = 10.0
    scale_jump_upper_ratio: float = 10.0
    scale_drop_lower_ratio: float = 0.05
    min_sample_size: int = MIN_PSI_SAMPLE
    min_slice_sample_size: int = 30


@dataclass
class ActionableResponse:
    """Actionable Alert-to-Response statement per Lecture 4 Q22."""

    recommended_action: str
    owner: str
    affected_features: list[dict[str, Any]] = field(default_factory=list)
    affected_slices: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class DriftReport:
    """Structured `drift-report.v1` payload."""

    schema_version: str
    run_id: str
    created_at: str
    current_snapshot_path: str
    baseline_snapshot_path: str
    current_snapshot_version: str
    baseline_snapshot_version: str
    current_row_count: int
    baseline_row_count: int
    comparison_scope: str
    comparison_current_rows: int
    comparison_baseline_rows: int
    volume_ratio: float
    schema_valid: bool
    schema_errors: list[str]
    ground_truth_available: bool
    semantic_anomaly_detected: bool
    semantic_anomalies: list[str]
    scale_ratios: dict[str, dict[str, float]]
    null_fraction_current: dict[str, float]
    null_fraction_baseline: dict[str, float]
    null_delta_by_feature: dict[str, float]
    psi_by_feature: dict[str, float]
    ks_by_feature: dict[str, dict[str, float]]
    max_psi: float
    max_psi_feature: str
    max_ks_stat: float
    max_ks_feature: str
    label_rate_current: float | None
    label_rate_baseline: float
    label_rate_delta: float
    insufficient_data_rate_current: float
    insufficient_data_rate_baseline: float
    insufficient_data_rate_delta: float
    slice_psi_by_module: dict[str, float]
    slice_shift_pattern: str
    decision: str
    recommended_action: str
    actionable_response: ActionableResponse

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_snapshot_version(snapshot_path: Path) -> str:
    ledger_path = snapshot_path.parent / f"{snapshot_path.stem}.ledger.json"
    if ledger_path.is_file():
        try:
            data = json.loads(ledger_path.read_text(encoding="utf-8"))
            version = data.get("snapshot_version")
            if isinstance(version, str) and version:
                return version
        except (OSError, ValueError):
            pass
    return "unknown"


class DriftMonitor:
    """Evaluates schema/semantic integrity, covariate shift, slice PSI, and triage decision."""

    def __init__(self, thresholds: DriftThresholds | None = None) -> None:
        self.thresholds = thresholds or DriftThresholds()

    def evaluate(
        self,
        current_snapshot_path: Path | str,
        baseline_snapshot_path: Path | str,
        run_id: str = "drift-check",
    ) -> DriftReport:
        run_id = _validate_run_id(run_id)
        cur_path = Path(current_snapshot_path)
        base_path = Path(baseline_snapshot_path)

        cur_df = pd.read_parquet(cur_path)
        base_df = pd.read_parquet(base_path)

        cur_version = _read_snapshot_version(cur_path)
        base_version = _read_snapshot_version(base_path)

        schema_errors: list[str] = []
        semantic_anomalies: list[str] = []
        ground_truth_available = True

        # 1. Schema & Domain Invariants + Delayed Ground Truth Check (ASM-03)
        missing_cols = [c for c in EXPECTED_COLUMNS if c not in cur_df.columns]
        if missing_cols:
            schema_errors.append(f"missing_columns:{','.join(missing_cols)}")
            ground_truth_available = False
        else:
            if cur_df.empty:
                schema_errors.append("empty_current_snapshot")
                ground_truth_available = False

            non_null_labels = cur_df["label"].dropna()
            if not non_null_labels.isin([0, 1]).all():
                schema_errors.append("label_out_of_domain")
            if cur_df["label"].isna().any() or len(non_null_labels) == 0:
                # ASM-03: Delayed ground truth at week-4 cutoff before end-of-semester final_result
                ground_truth_available = False

            if not cur_df["split"].isin(VALID_SPLITS).all():
                bad_splits = sorted(
                    cur_df.loc[~cur_df["split"].isin(VALID_SPLITS), "split"]
                    .astype(str)
                    .unique()
                )
                schema_errors.append(f"split_out_of_domain:{','.join(bad_splits)}")
            dup_mask = cur_df.duplicated(subset=list(KEYS), keep=False)
            if dup_mask.any():
                schema_errors.append(f"duplicate_composite_keys:{int(dup_mask.sum())}")

            # Physical domain invariants
            for col in NUMERIC_FEATURES:
                if not pd.api.types.is_numeric_dtype(cur_df[col]):
                    schema_errors.append(f"non_numeric_dtype:{col}")
            if not schema_errors:
                if (cur_df["n_clicks_before_cutoff"].dropna() < 0).any():
                    semantic_anomalies.append("negative_clicks_before_cutoff")
                if (cur_df["n_submitted_before_cutoff"].dropna() < 0).any():
                    semantic_anomalies.append("negative_submissions_before_cutoff")
                scores = cur_df["avg_score_submitted"].dropna()
                if not scores.empty and ((scores < 0.0) | (scores > 100.0)).any():
                    semantic_anomalies.append("avg_score_submitted_out_of_bounds_0_100")

        schema_valid = len(schema_errors) == 0

        # 2. Volume & Missingness Check
        base_len = max(len(base_df), 1)
        volume_ratio = round(len(cur_df) / base_len, 4)
        if (
            volume_ratio < self.thresholds.min_volume_ratio
            or volume_ratio > self.thresholds.max_volume_ratio
        ):
            semantic_anomalies.append(
                f"volume_ratio_out_of_bounds:{volume_ratio:.4f}"
                f":allowed=[{self.thresholds.min_volume_ratio},{self.thresholds.max_volume_ratio}]"
            )

        null_cur: dict[str, float] = {}
        null_base: dict[str, float] = {}
        null_delta: dict[str, float] = {}
        check_features = [
            c
            for c in ORIGINAL_FEATURES
            if c in cur_df.columns and c in base_df.columns
        ]
        for col in check_features:
            c_null = float(cur_df[col].isna().mean()) if len(cur_df) else 1.0
            b_null = float(base_df[col].isna().mean()) if len(base_df) else 0.0
            null_cur[col] = round(c_null, 4)
            null_base[col] = round(b_null, 4)
            null_delta[col] = round(c_null - b_null, 4)
            if c_null > self.thresholds.max_null_fraction:
                semantic_anomalies.append(
                    f"missingness_exceeded:{col}:{c_null:.4f}>{self.thresholds.max_null_fraction}"
                )

        # 3. Semantic Scale Anomaly Guard (Lecture 4 Q05/Q12)
        scale_ratios: dict[str, dict[str, float]] = {}
        if schema_valid and not base_df.empty and not cur_df.empty:
            for col in ("n_clicks_before_cutoff", "n_submitted_before_cutoff"):
                cur_s = pd.to_numeric(cur_df[col], errors="coerce").dropna()
                base_s = pd.to_numeric(base_df[col], errors="coerce").dropna()
                if cur_s.empty or base_s.empty:
                    continue
                cur_med = float(np.median(cur_s))
                base_med = float(np.median(base_s))
                cur_p95 = float(np.quantile(cur_s, 0.95))
                base_p95 = float(np.quantile(base_s, 0.95))

                med_ratio = (
                    (cur_med / base_med)
                    if base_med > 0
                    else (1.0 if cur_med == 0 else 999.0)
                )
                p95_ratio = (
                    (cur_p95 / base_p95)
                    if base_p95 > 0
                    else (1.0 if cur_p95 == 0 else 999.0)
                )
                scale_ratios[col] = {
                    "current_median": round(cur_med, 4),
                    "baseline_median": round(base_med, 4),
                    "median_ratio": round(med_ratio, 4),
                    "current_p95": round(cur_p95, 4),
                    "baseline_p95": round(base_p95, 4),
                    "p95_ratio": round(p95_ratio, 4),
                }
                if (
                    med_ratio > self.thresholds.scale_jump_upper_ratio
                    or p95_ratio > self.thresholds.scale_jump_upper_ratio
                ):
                    semantic_anomalies.append(
                        f"semantic_scale_explosion:{col}:median_ratio={med_ratio:.2f}x:p95_ratio={p95_ratio:.2f}x"
                    )
                elif base_med > 1.0 and (
                    med_ratio < self.thresholds.scale_drop_lower_ratio
                    or p95_ratio < self.thresholds.scale_drop_lower_ratio
                ):
                    semantic_anomalies.append(
                        f"semantic_scale_collapse:{col}:median_ratio={med_ratio:.3f}x:p95_ratio={p95_ratio:.3f}x"
                    )

        semantic_anomaly_detected = len(semantic_anomalies) > 0

        # 4. Select comparison cohort (validation split if >= min_sample_size, else full snapshot)
        if schema_valid and "split" in cur_df.columns and "split" in base_df.columns:
            cur_val = cur_df[cur_df["split"] == "validation"]
            base_val = base_df[base_df["split"] == "validation"]
            if (
                len(cur_val) >= self.thresholds.min_sample_size
                and len(base_val) >= self.thresholds.min_sample_size
            ):
                comp_cur = cur_val
                comp_base = base_val
                comparison_scope = "validation"
            else:
                comp_cur = cur_df
                comp_base = base_df
                comparison_scope = "full_snapshot"
        else:
            comp_cur = cur_df
            comp_base = base_df
            comparison_scope = "full_snapshot"

        # 5. Compute PSI and Two-Sample KS statistics
        psi_by_feature: dict[str, float] = {}
        ks_by_feature: dict[str, dict[str, float]] = {}

        if (
            schema_valid
            and len(comp_cur) >= self.thresholds.min_sample_size
            and len(comp_base) >= self.thresholds.min_sample_size
        ):
            for col in NUMERIC_FEATURES:
                if col not in comp_cur.columns or col not in comp_base.columns:
                    continue
                psi = _psi_numeric(comp_base[col], comp_cur[col])
                psi_by_feature[col] = round(float(psi), 4)
                base_num = pd.to_numeric(comp_base[col], errors="coerce").dropna()
                cur_num = pd.to_numeric(comp_cur[col], errors="coerce").dropna()
                if len(base_num) >= 2 and len(cur_num) >= 2:
                    ks_res = ks_2samp(base_num.to_numpy(), cur_num.to_numpy())
                    ks_by_feature[col] = {
                        "ks_stat": round(float(ks_res.statistic), 4),
                        "ks_pvalue": round(float(ks_res.pvalue), 6),
                    }
                else:
                    ks_by_feature[col] = {"ks_stat": 0.0, "ks_pvalue": 1.0}

            for col in CATEGORICAL_FEATURES:
                if col not in comp_cur.columns or col not in comp_base.columns:
                    continue
                psi = _psi_categorical(comp_base[col], comp_cur[col])
                psi_by_feature[col] = round(float(psi), 4)

        max_psi = max(psi_by_feature.values(), default=0.0)
        max_psi_feature = (
            max(psi_by_feature.items(), key=lambda kv: kv[1])[0]
            if psi_by_feature
            else ""
        )
        max_ks_stat = max(
            (v["ks_stat"] for v in ks_by_feature.values()), default=0.0
        )
        max_ks_feature = (
            max(ks_by_feature.items(), key=lambda kv: kv[1]["ks_stat"])[0]
            if ks_by_feature
            else ""
        )

        # 6. Label-Prior & Insufficient-Data Shift
        label_cur: float | None = None
        if schema_valid and len(cur_df) > 0 and len(base_df) > 0:
            label_base = float(base_df["label"].dropna().mean())
            if ground_truth_available:
                label_cur = float(cur_df["label"].mean())
                label_delta = round(abs(label_cur - label_base), 4)
            else:
                label_cur = None
                label_delta = 0.0
            insuff_cur = float(cur_df["insufficient_data"].astype(bool).mean())
            insuff_base = float(base_df["insufficient_data"].astype(bool).mean())
        else:
            label_base = insuff_cur = insuff_base = label_delta = 0.0

        insuff_delta = round(abs(insuff_cur - insuff_base), 4)

        # 7. Slice-Level Drift Diagnosis (Lecture 4 Q21)
        slice_psi_by_module: dict[str, float] = {}
        if (
            schema_valid
            and "code_module" in cur_df.columns
            and "code_module" in base_df.columns
        ):
            common_modules = sorted(
                set(cur_df["code_module"].astype(str).unique())
                & set(base_df["code_module"].astype(str).unique())
            )
            for mod in common_modules:
                mod_cur = cur_df[cur_df["code_module"] == mod]
                mod_base = base_df[base_df["code_module"] == mod]
                if (
                    len(mod_cur) < self.thresholds.min_slice_sample_size
                    or len(mod_base) < self.thresholds.min_slice_sample_size
                ):
                    continue
                mod_psis: list[float] = []
                for col in (
                    "n_clicks_before_cutoff",
                    "avg_score_submitted",
                    "click_trend_w3_w4",
                ):
                    if col in mod_cur.columns and col in mod_base.columns:
                        mod_psis.append(
                            float(_psi_numeric(mod_base[col], mod_cur[col]))
                        )
                if mod_psis:
                    slice_psi_by_module[mod] = round(max(mod_psis), 4)

        affected_slices = sorted(
            mod
            for mod, s_psi in slice_psi_by_module.items()
            if s_psi > self.thresholds.psi_fail_threshold
        )
        if not affected_slices:
            slice_shift_pattern = "none"
        elif len(affected_slices) < max(len(slice_psi_by_module), 1):
            slice_shift_pattern = "localized_slice_shift"
        else:
            slice_shift_pattern = "global_cohort_shift"

        # 8. Triage Decision Engine & Actionable Alert-to-Response Statement (Lecture 4 Q20 & Q22)
        affected_features: list[dict[str, Any]] = []
        for col, psi_val in sorted(psi_by_feature.items(), key=lambda kv: -kv[1]):
            ks_info = ks_by_feature.get(col, {})
            ks_stat_val = ks_info.get("ks_stat", 0.0)
            ks_pval = ks_info.get("ks_pvalue", 1.0)
            if psi_val > self.thresholds.psi_warn_threshold or (
                ks_stat_val > self.thresholds.ks_stat_threshold
                and ks_pval < self.thresholds.ks_pvalue_threshold
            ):
                affected_features.append({
                    "feature": col,
                    "psi": psi_val,
                    "ks_stat": ks_stat_val,
                    "ks_pvalue": ks_pval,
                })

        ks_triggered = any(
            v["ks_stat"] > self.thresholds.ks_stat_threshold
            and v["ks_pvalue"] < self.thresholds.ks_pvalue_threshold
            for v in ks_by_feature.values()
        )
        drift_exceeded = (
            max_psi > self.thresholds.psi_fail_threshold
            or ks_triggered
            or (
                ground_truth_available
                and label_delta > self.thresholds.label_rate_delta_threshold
            )
        )

        if not schema_valid or semantic_anomaly_detected:
            decision = DECISION_QUALITY_FAILURE
            recommended_action = ACTION_QUARANTINE_SAFE_MODE
            reasons = schema_errors + semantic_anomalies
            actionable = ActionableResponse(
                recommended_action=ACTION_QUARANTINE_SAFE_MODE,
                owner="data_engineer",
                affected_features=affected_features,
                affected_slices=affected_slices,
                rationale=(
                    "Data quality or semantic scale violation detected "
                    f"({'; '.join(reasons)}). Retraining is strictly forbidden per "
                    "CMU MLIP Lecture 4 Q20 to prevent poisoning the Champion model."
                ),
            )
        elif drift_exceeded and not ground_truth_available:
            # ASM-03 (Delayed Ground Truth): Live week-4 cohort has covariate shift
            # but end-of-semester final_result labels are not available yet.
            decision = DECISION_WARN_MONITOR
            recommended_action = ACTION_SCORE_AWAIT_LABELS
            actionable = ActionableResponse(
                recommended_action=ACTION_SCORE_AWAIT_LABELS,
                owner="mlops_engineer",
                affected_features=affected_features,
                affected_slices=affected_slices,
                rationale=(
                    f"Significant covariate shift detected (max_psi={max_psi:.4f} on "
                    f"'{max_psi_feature}', max_ks={max_ks_stat:.4f}), but ground-truth "
                    "labels (final_result) are not yet available at week-4 cutoff (ASM-03). "
                    "Per Lecture 4 Q20, blind retraining without ground truth is blocked; "
                    "score with incumbent Champion, monitor realized alert rate, and trigger "
                    "retraining once verified semester labels arrive."
                ),
            )
        elif drift_exceeded:
            decision = DECISION_DRIFT_RETRAIN
            recommended_action = ACTION_TRIGGER_RETRAINING
            actionable = ActionableResponse(
                recommended_action=ACTION_TRIGGER_RETRAINING,
                owner="mlops_engineer",
                affected_features=affected_features,
                affected_slices=affected_slices,
                rationale=(
                    f"Significant distribution shift verified on clean schema with ground truth "
                    f"(max_psi={max_psi:.4f} on '{max_psi_feature}', "
                    f"max_ks={max_ks_stat:.4f} on '{max_ks_feature}', "
                    f"label_rate_delta={label_delta:.4f}, pattern={slice_shift_pattern}). "
                    "Triggering Challenger retraining and 3-layer Champion-vs-Challenger gates."
                ),
            )
        elif max_psi > self.thresholds.psi_warn_threshold:
            decision = DECISION_WARN_MONITOR
            recommended_action = (
                ACTION_SCORE_AND_MONITOR
                if ground_truth_available
                else ACTION_SCORE_AWAIT_LABELS
            )
            actionable = ActionableResponse(
                recommended_action=recommended_action,
                owner="mlops_engineer",
                affected_features=affected_features,
                affected_slices=affected_slices,
                rationale=(
                    f"Moderate covariate shift detected (max_psi={max_psi:.4f} on "
                    f"'{max_psi_feature}' in warn range "
                    f"({self.thresholds.psi_warn_threshold}, {self.thresholds.psi_fail_threshold}]). "
                    "Continue scoring with incumbent Champion and monitor alert rate."
                ),
            )
        else:
            decision = DECISION_NO_DRIFT
            recommended_action = ACTION_SCORE_CHAMPION
            actionable = ActionableResponse(
                recommended_action=ACTION_SCORE_CHAMPION,
                owner="mlops_engineer",
                affected_features=affected_features,
                affected_slices=affected_slices,
                rationale=(
                    f"Feature distributions are stable relative to baseline "
                    f"(max_psi={max_psi:.4f} <= {self.thresholds.psi_warn_threshold}). "
                    "Score directly with the incumbent Champion release."
                ),
            )

        return DriftReport(
            schema_version=DRIFT_REPORT_SCHEMA_VERSION,
            run_id=run_id,
            created_at=datetime.now(UTC).isoformat(),
            current_snapshot_path=str(cur_path),
            baseline_snapshot_path=str(base_path),
            current_snapshot_version=cur_version,
            baseline_snapshot_version=base_version,
            current_row_count=len(cur_df),
            baseline_row_count=len(base_df),
            comparison_scope=comparison_scope,
            comparison_current_rows=len(comp_cur),
            comparison_baseline_rows=len(comp_base),
            volume_ratio=volume_ratio,
            schema_valid=schema_valid,
            schema_errors=schema_errors,
            ground_truth_available=ground_truth_available,
            semantic_anomaly_detected=semantic_anomaly_detected,
            semantic_anomalies=semantic_anomalies,
            scale_ratios=scale_ratios,
            null_fraction_current=null_cur,
            null_fraction_baseline=null_base,
            null_delta_by_feature=null_delta,
            psi_by_feature=psi_by_feature,
            ks_by_feature=ks_by_feature,
            max_psi=round(max_psi, 4),
            max_psi_feature=max_psi_feature,
            max_ks_stat=round(max_ks_stat, 4),
            max_ks_feature=max_ks_feature,
            label_rate_current=(
                round(label_cur, 4) if label_cur is not None else None
            ),
            label_rate_baseline=round(label_base, 4),
            label_rate_delta=label_delta,
            insufficient_data_rate_current=round(insuff_cur, 4),
            insufficient_data_rate_baseline=round(insuff_base, 4),
            insufficient_data_rate_delta=insuff_delta,
            slice_psi_by_module=slice_psi_by_module,
            slice_shift_pattern=slice_shift_pattern,
            decision=decision,
            recommended_action=recommended_action,
            actionable_response=actionable,
        )


def format_drift_markdown(report: DriftReport) -> str:
    """Render a human-readable Markdown summary for `drift_summary.md`."""
    lines = [
        f"# LearnGuard Drift Triage Report (`{report.run_id}`)",
        "",
        f"- **Schema Version:** `{report.schema_version}`",
        f"- **Created At:** `{report.created_at}`",
        f"- **Decision:** `{report.decision}`",
        f"- **Recommended Action:** `{report.recommended_action}`",
        f"- **Ground Truth Available (`ASM-03`):** `{report.ground_truth_available}`",
        f"- **Owner:** `{report.actionable_response.owner}`",
        f"- **Current Snapshot:** `{report.current_snapshot_version}` ({report.current_row_count} rows)",
        f"- **Baseline Snapshot:** `{report.baseline_snapshot_version}` ({report.baseline_row_count} rows)",
        f"- **Volume Ratio:** `{report.volume_ratio:.4f}`",
        (
            f"- **Comparison Scope:** `{report.comparison_scope}` "
            f"(current={report.comparison_current_rows}, baseline={report.comparison_baseline_rows})"
        ),
        "",
        "## 1. Triage Rationale",
        "",
        f"> {report.actionable_response.rationale}",
        "",
        "## 2. Schema & Semantic Integrity Guard",
        "",
        f"- **Schema Valid:** `{report.schema_valid}`",
        f"- **Semantic Anomaly Detected:** `{report.semantic_anomaly_detected}`",
    ]
    if report.schema_errors:
        lines.append(f"- **Schema Errors:** `{', '.join(report.schema_errors)}`")
    if report.semantic_anomalies:
        lines.append(
            f"- **Semantic Anomalies:** `{', '.join(report.semantic_anomalies)}`"
        )

    lines.extend([
        "",
        "## 3. Top Feature Drift Metrics (PSI & KS)",
        "",
        "| Feature | PSI | KS Stat | KS p-value | Null Delta |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ])
    for feat, psi_val in sorted(report.psi_by_feature.items(), key=lambda kv: -kv[1]):
        ks_entry = report.ks_by_feature.get(feat, {})
        ks_s = ks_entry.get("ks_stat", 0.0)
        ks_p = ks_entry.get("ks_pvalue", 1.0)
        n_delta = report.null_delta_by_feature.get(feat, 0.0)
        lines.append(
            f"| `{feat}` | {psi_val:.4f} | {ks_s:.4f} | {ks_p:.6f} | {n_delta:+.4f} |"
        )

    lines.extend([
        "",
        "## 4. Slice-Level Drift Diagnosis (`code_module`)",
        "",
        f"- **Shift Pattern:** `{report.slice_shift_pattern}`",
    ])
    for mod, s_psi in sorted(report.slice_psi_by_module.items()):
        lines.append(f"- Module `{mod}`: max PSI = `{s_psi:.4f}`")

    return "\n".join(lines) + "\n"


def publish_drift_report(
    artifacts_dir: Path | str,
    report: DriftReport,
) -> Path:
    """Atomically publish `drift_report.json`, `drift_summary.md`, `manifest.json`, `success.json`."""
    run_id = _validate_run_id(report.run_id)
    root = Path(artifacts_dir) / DRIFT_REPORTS_DIRNAME
    target = root / run_id
    if target.exists():
        raise FileExistsError(f"drift_report_run_id_exists:{run_id}")
    root.mkdir(parents=True, exist_ok=True)
    staging = root / f".{run_id}.staging-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        report_path = staging / "drift_report.json"
        summary_path = staging / "drift_summary.md"
        manifest_path = staging / "manifest.json"
        success_path = staging / "success.json"

        report_path.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary_path.write_text(format_drift_markdown(report), encoding="utf-8")

        files = {
            "drift_report.json": _file_hash(report_path),
            "drift_summary.md": _file_hash(summary_path),
        }
        manifest = {
            "schema_version": DRIFT_REPORT_SCHEMA_VERSION,
            "run_id": run_id,
            "decision": report.decision,
            "recommended_action": report.recommended_action,
            "files": files,
            "created_at": report.created_at,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        success_path.write_text(
            json.dumps(
                {
                    "schema_version": DRIFT_REPORT_SCHEMA_VERSION,
                    "run_id": run_id,
                    "decision": report.decision,
                    "manifest_sha256": _file_hash(manifest_path),
                    "drift_report_sha256": files["drift_report.json"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if target.exists():
            raise FileExistsError(f"drift_report_run_id_exists:{run_id}")
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LearnGuard MLOps Multi-Layer Data Drift & Semantic Anomaly Monitor"
    )
    parser.add_argument(
        "--snapshot", required=True, type=Path, help="Current snapshot.parquet"
    )
    parser.add_argument(
        "--baseline-snapshot",
        required=True,
        type=Path,
        help="Baseline snapshot.parquet",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("artifacts"),
        help="Artifacts root directory",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run ID for drift report publication",
    )
    parser.add_argument(
        "--min-sample-size",
        type=int,
        default=MIN_PSI_SAMPLE,
        help="Minimum sample size for PSI/KS evaluation",
    )
    args = parser.parse_args(argv)

    run_id = args.run_id or datetime.now(UTC).strftime("drift-%Y%m%dT%H%M%SZ")
    thresholds = DriftThresholds(min_sample_size=args.min_sample_size)
    monitor = DriftMonitor(thresholds=thresholds)
    report = monitor.evaluate(
        args.snapshot, args.baseline_snapshot, run_id=run_id
    )
    published_dir = publish_drift_report(args.artifacts_dir, report)
    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "decision": report.decision,
                "recommended_action": report.recommended_action,
                "ground_truth_available": report.ground_truth_available,
                "max_psi": report.max_psi,
                "max_psi_feature": report.max_psi_feature,
                "semantic_anomaly_detected": report.semantic_anomaly_detected,
                "published_dir": str(published_dir),
            },
            indent=2,
        )
    )
    return 1 if report.decision == DECISION_QUALITY_FAILURE else 0


if __name__ == "__main__":
    raise SystemExit(main())
