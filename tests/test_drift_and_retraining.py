"""End-to-end automated tests for LearnGuard Drift Detection, Simulation & Continual Retraining.

Verifies CMU MLIP Lecture 4-6 requirements:
  1. Cold-start bootstrap trains initial Champion, passes 3-layer Evaluation Gates
     (Data + ML + Behavioral), packages immutable `model-release.v1`, writes
     `active_release.json`, and scores M5 (`prediction-batch.v1`).
  2. `baseline_no_drift` scenario detects `NO_DRIFT` and scores with the incumbent
     Champion without retraining.
  3. `gradual_covariate_drift` scenario detects `DRIFT_RETRAIN_RECOMMENDED` (PSI > 0.20),
     trains Challenger, passes all 3 gates (including `regression_vs_baseline` and
     honest `drift_vs_baseline` warn status in `eval_data.json`), promotes Challenger
     into `active_release.json` (preserving `previous_release`), and scores M5.
  4. `new_semester_cohort` scenario runs full M1->M2->M3->Drift->M4->Gates->Release->M5
     on an expanded cohort and updates `active_release.json`.
  5. `corrupted_feed_quarantine` scenario (Lecture 4 Q05/Q12/Q20) detects 50x semantic
     scale explosion (`DATA_QUALITY_OR_SEMANTIC_FAILURE`), blocks retraining, enters
     Safe Mode, and keeps the Champion untouched!
  6. `rejected_challenger_guard` scenario fails `MLGate`, rejects the Challenger, and
     retains the incumbent Champion in `active_release.json`.
  7. `--mode rollback` restores the previous Champion release in `active_release.json`
     and scores M5.
  8. `ASM-03` Delayed Ground Truth: an unlabeled week-4 cohort with covariate shift
     (`PSI > 0.20` and `label` as `NaN`) returns `WARN_MONITOR` +
     `SCORE_WITH_CHAMPION_AWAIT_LABELS` instead of blind retraining without labels.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from learnguard.ml.contracts import load_prediction_batch_manifest
from learnguard.ml.release import load_and_verify_model_release

from deploy.ml.data_simulator import generate_oulad_dataset
from deploy.ml.drift_monitor import (
    ACTION_QUARANTINE_SAFE_MODE,
    ACTION_SCORE_AWAIT_LABELS,
    ACTION_SCORE_CHAMPION,
    ACTION_TRIGGER_RETRAINING,
    DECISION_DRIFT_RETRAIN,
    DECISION_NO_DRIFT,
    DECISION_QUALITY_FAILURE,
    DECISION_WARN_MONITOR,
    DRIFT_REPORT_SCHEMA_VERSION,
    DriftMonitor,
)
from deploy.ml.retrain_pipeline import (
    build_parser,
    load_active_release_pointer,
    run_continual_pipeline,
)


def test_continual_learning_all_five_scenarios_and_rollback_end_to_end(
    tmp_path: Path,
) -> None:
    """Verify cold-start bootstrap + all 5 simulation scenarios + rollback across the continual pipeline."""
    artifacts_dir = tmp_path / "artifacts"
    data_root = tmp_path / "data"

    # --- Phase 0: Cold-Start Bootstrap ---
    base_dir = data_root / "00_bootstrap"
    sim_base = generate_oulad_dataset(
        base_dir, "baseline_no_drift", students_per_presentation=250, seed=42
    )
    assert sim_base.split_counts["validation"] >= 200

    code_boot, rep_boot = run_continual_pipeline(
        base_dir, artifacts_dir, mode="auto", run_id="run-00-bootstrap"
    )
    assert code_boot == 0
    assert rep_boot.outcome == "BOOTSTRAPPED_CHAMPION"
    assert rep_boot.promoted_new_release is True
    assert rep_boot.active_release_id == "release-run-00-bootstrap"
    assert rep_boot.previous_release_id is None

    pointer_boot = load_active_release_pointer(artifacts_dir)
    assert pointer_boot is not None
    champ_0 = pointer_boot["current_release"]
    assert champ_0["release_id"] == "release-run-00-bootstrap"
    assert pointer_boot["previous_release"] is None

    # Verify immutable release artifact contract
    verified_rel_0 = load_and_verify_model_release(
        champ_0["release_dir"], champ_0["baseline_snapshot_path"]
    )
    assert verified_rel_0.release_id == "release-run-00-bootstrap"

    # --- Scenario 1: baseline_no_drift -> NO_DRIFT, Score with Champion without retraining ---
    s1_dir = data_root / "01_baseline_no_drift"
    generate_oulad_dataset(
        s1_dir, "baseline_no_drift", students_per_presentation=250, seed=42
    )
    code_s1, rep_s1 = run_continual_pipeline(
        s1_dir, artifacts_dir, mode="auto", run_id="run-01-no-drift"
    )
    assert code_s1 == 0
    assert rep_s1.drift_decision == DECISION_NO_DRIFT
    assert rep_s1.recommended_action == ACTION_SCORE_CHAMPION
    assert rep_s1.outcome == "SCORED_WITH_CHAMPION"
    assert rep_s1.promoted_new_release is False
    assert rep_s1.active_release_id == "release-run-00-bootstrap"
    assert rep_s1.scored_rows > 0

    # Verify drift report artifact was atomically published
    assert rep_s1.drift_report_dir is not None
    drift_json_s1 = json.loads(
        (Path(rep_s1.drift_report_dir) / "drift_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert drift_json_s1["schema_version"] == DRIFT_REPORT_SCHEMA_VERSION
    assert drift_json_s1["decision"] == DECISION_NO_DRIFT
    assert drift_json_s1["ground_truth_available"] is True
    assert drift_json_s1["max_psi"] == 0.0

    # --- Scenario 2: corrupted_feed_quarantine -> DATA_QUALITY_OR_SEMANTIC_FAILURE (Safe Mode) ---
    s2_dir = data_root / "02_corrupted_feed"
    generate_oulad_dataset(
        s2_dir,
        "corrupted_feed_quarantine",
        students_per_presentation=250,
        seed=42,
    )
    code_s2, rep_s2 = run_continual_pipeline(
        s2_dir, artifacts_dir, mode="auto", run_id="run-02-corrupted"
    )
    assert code_s2 == 1
    assert rep_s2.drift_decision == DECISION_QUALITY_FAILURE
    assert rep_s2.recommended_action == ACTION_QUARANTINE_SAFE_MODE
    assert rep_s2.outcome == "QUARANTINE_AND_SAFE_MODE"
    assert rep_s2.promoted_new_release is False

    # Verify Champion in active_release.json was NOT touched by corrupted data (Lecture 4 Q20)
    pointer_after_s2 = load_active_release_pointer(artifacts_dir)
    assert pointer_after_s2 is not None
    assert (
        pointer_after_s2["current_release"]["release_id"]
        == "release-run-00-bootstrap"
    )

    drift_json_s2 = json.loads(
        (Path(rep_s2.drift_report_dir) / "drift_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert drift_json_s2["semantic_anomaly_detected"] is True
    assert any(
        "semantic_scale_explosion" in a
        for a in drift_json_s2["semantic_anomalies"]
    )

    # --- Scenario 3: gradual_covariate_drift -> DRIFT_RETRAIN_RECOMMENDED & PROMOTE_CHALLENGER ---
    s3_dir = data_root / "03_gradual_drift"
    generate_oulad_dataset(
        s3_dir,
        "gradual_covariate_drift",
        students_per_presentation=250,
        seed=42,
    )
    code_s3, rep_s3 = run_continual_pipeline(
        s3_dir, artifacts_dir, mode="auto", run_id="run-03-gradual-drift"
    )
    assert code_s3 == 0
    assert rep_s3.drift_decision == DECISION_DRIFT_RETRAIN
    assert rep_s3.recommended_action == ACTION_TRIGGER_RETRAINING
    assert rep_s3.outcome == "PROMOTE_CHALLENGER"
    assert rep_s3.promoted_new_release is True
    assert rep_s3.active_release_id == "release-run-03-gradual-drift"
    assert rep_s3.previous_release_id == "release-run-00-bootstrap"

    # Verify all 3 evaluation scorecards were published for the promoted Challenger
    eval_dir_s3 = Path(rep_s3.evaluation_dir)
    assert (eval_dir_s3 / "eval_data.json").is_file()
    assert (eval_dir_s3 / "eval_ml.json").is_file()
    assert (eval_dir_s3 / "eval_behavioral.json").is_file()
    assert rep_s3.gate_summaries["data"]["fail"] == 0
    assert rep_s3.gate_summaries["ml"]["fail"] == 0
    assert rep_s3.gate_summaries["behavioral"]["fail"] == 0

    # Verify H-04.3: eval_data.json honestly records real PSI (> 0.20) as status="warn"
    eval_data_s3 = json.loads(
        (eval_dir_s3 / "eval_data.json").read_text(encoding="utf-8")
    )
    drift_chk_s3 = next(
        chk
        for chk in eval_data_s3["checks"]
        if chk["id"] == "drift_vs_baseline"
    )
    assert drift_chk_s3["status"] == "warn"
    assert drift_chk_s3["observed"]["max_psi"] > 0.20
    assert drift_chk_s3["observed"]["authorized_retraining_trigger"] is True

    # Verify prediction batch manifest for M5 scoring
    batch_manifest_s3 = load_prediction_batch_manifest(
        Path(rep_s3.prediction_batch_dir) / "manifest.json"
    )
    assert batch_manifest_s3.run_id == "run-03-gradual-drift"
    assert batch_manifest_s3.row_count == 250 * 4

    # --- Scenario 4: rejected_challenger_guard -> Fails MLGate & keeps Champion ---
    s4_dir = data_root / "04_rejected_challenger"
    generate_oulad_dataset(
        s4_dir,
        "rejected_challenger_guard",
        students_per_presentation=250,
        seed=42,
    )
    # Compare against original bootstrap baseline so drift triggers retraining on noisy cohort
    code_s4, rep_s4 = run_continual_pipeline(
        s4_dir,
        artifacts_dir,
        mode="auto",
        baseline_snapshot_path=champ_0["baseline_snapshot_path"],
        run_id="run-04-rejected-challenger",
    )
    assert code_s4 == 1
    assert rep_s4.drift_decision == DECISION_DRIFT_RETRAIN
    assert rep_s4.outcome == "REJECT_CHALLENGER_KEEP_CHAMPION"
    assert rep_s4.promoted_new_release is False
    assert rep_s4.gate_summaries["ml"]["fail"] >= 1

    # Verify incumbent Champion from Scenario 3 is still active
    pointer_after_s4 = load_active_release_pointer(artifacts_dir)
    assert pointer_after_s4 is not None
    assert (
        pointer_after_s4["current_release"]["release_id"]
        == "release-run-03-gradual-drift"
    )
    assert (
        pointer_after_s4["previous_release"]["release_id"]
        == "release-run-00-bootstrap"
    )

    # --- Scenario 5: new_semester_cohort -> Expanded cohort triggers full retrain & promotion ---
    s5_dir = data_root / "05_new_semester_cohort"
    sim_s5 = generate_oulad_dataset(
        s5_dir, "new_semester_cohort", students_per_presentation=250, seed=99
    )
    assert sim_s5.total_students > 1000
    code_s5, rep_s5 = run_continual_pipeline(
        s5_dir,
        artifacts_dir,
        mode="auto",
        baseline_snapshot_path=champ_0["baseline_snapshot_path"],
        run_id="run-05-new-semester",
    )
    assert code_s5 == 0
    assert rep_s5.drift_decision == DECISION_DRIFT_RETRAIN
    assert rep_s5.outcome == "PROMOTE_CHALLENGER"
    assert rep_s5.promoted_new_release is True
    assert rep_s5.active_release_id == "release-run-05-new-semester"
    assert rep_s5.previous_release_id == "release-run-03-gradual-drift"

    # --- Phase 6: Model Rollback (--mode rollback) ---
    parser = build_parser()
    parsed = parser.parse_args([
        "--mode",
        "rollback",
        "--rollback-release",
        "release-run-03-gradual-drift",
        "--artifacts-dir",
        str(artifacts_dir),
    ])
    assert parsed.mode == "rollback"
    assert parsed.target_release_id == "release-run-03-gradual-drift"

    code_rb, rep_rb = run_continual_pipeline(
        s5_dir,
        artifacts_dir,
        mode="rollback",
        target_release_id="release-run-03-gradual-drift",
        run_id="run-06-rollback",
    )
    assert code_rb == 0
    assert rep_rb.outcome == "ROLLED_BACK_RELEASE"
    assert rep_rb.active_release_id == "release-run-03-gradual-drift"
    assert rep_rb.previous_release_id == "release-run-05-new-semester"
    assert rep_rb.scored_rows > 0

    pointer_after_rb = load_active_release_pointer(artifacts_dir)
    assert pointer_after_rb is not None
    assert (
        pointer_after_rb["current_release"]["release_id"]
        == "release-run-03-gradual-drift"
    )


def test_delayed_ground_truth_asm03_blocks_blind_retraining(
    tmp_path: Path,
) -> None:
    """Verify ASM-03 (Lecture 4 Q20): covariate drift without ground-truth labels returns WARN_MONITOR + SCORE_WITH_CHAMPION_AWAIT_LABELS."""
    base_snap_path = tmp_path / "baseline_snapshot.parquet"
    drifted_unlabeled_path = tmp_path / "unlabeled_week4_snapshot.parquet"

    rng = np.random.default_rng(42)
    n = 260
    base_df = pd.DataFrame({
        "code_module": ["AAA"] * n,
        "code_presentation": ["2014B"] * n,
        "id_student": list(range(1, n + 1)),
        "gender": ["M", "F"] * (n // 2),
        "region": ["Scotland"] * n,
        "highest_education": ["A Level or Equivalent"] * n,
        "imd_band": ["20-30%"] * n,
        "age_band": ["0-35"] * n,
        "num_of_prev_attempts": [0] * n,
        "studied_credits": [60] * n,
        "disability": ["N"] * n,
        "imd_band_missing": [False] * n,
        "module_presentation": ["AAA-2014B"] * n,
        "n_clicks_before_cutoff": rng.integers(30, 120, size=n).astype(float),
        "click_trend_w3_w4": rng.integers(-20, 40, size=n).astype(float),
        "n_submitted_before_cutoff": rng.integers(1, 4, size=n).astype(float),
        "avg_score_submitted": rng.uniform(50.0, 85.0, size=n),
        "insufficient_data": [False] * n,
        "final_result": ["Pass", "Fail"] * (n // 2),
        "label": [0, 1] * (n // 2),
        "split": ["validation"] * n,
    })
    base_df.to_parquet(base_snap_path, index=False)

    # Create shifted live week-4 cohort where final_result / label are not yet available (NaN)
    cur_df = base_df.copy()
    cur_df["n_clicks_before_cutoff"] = cur_df["n_clicks_before_cutoff"] * 2.5
    cur_df["avg_score_submitted"] = np.clip(
        cur_df["avg_score_submitted"] + 15.0, 0.0, 100.0
    )
    cur_df["label"] = np.nan
    cur_df.to_parquet(drifted_unlabeled_path, index=False)

    monitor = DriftMonitor()
    report = monitor.evaluate(
        drifted_unlabeled_path, base_snap_path, run_id="asm03-unlabeled-check"
    )
    assert report.schema_valid is True
    assert report.semantic_anomaly_detected is False
    assert report.ground_truth_available is False
    assert report.max_psi > 0.20
    assert report.decision == DECISION_WARN_MONITOR
    assert report.recommended_action == ACTION_SCORE_AWAIT_LABELS
    assert "ASM-03" in report.actionable_response.rationale
