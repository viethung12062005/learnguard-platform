#!/usr/bin/env python3
"""Controlled OULAD Data Drift & New-Cohort Simulator (`data_simulator.py`).

Generates deterministic, fast, realistic 7-CSV OULAD datasets (and/or snapshot
perturbations) in an isolated workspace for CI/CD testing, GameDay rehearsals
(CMU MLIP Lecture 6), and end-to-end continual retraining verification.

Supported Scenarios:
  1. `baseline_no_drift`:
     Baseline OULAD 7-CSV dataset with >= 250 students per split (`train`:
     2013B/2013J, `validation`: 2014B, `holdout`: 2014J) so `MIN_PSI_SAMPLE = 200`
     is satisfied. Realistic strong correlation between higher VLE clicks / higher
     early assessment scores and lower failure/withdrawal (`label = 0`).
  2. `gradual_covariate_drift`:
     Shifts feature distributions (`n_clicks_before_cutoff`, `click_trend_w3_w4`,
     `avg_score_submitted`, `studied_credits`, `region`) enough that `PSI > 0.25`
     (`DRIFT_RETRAIN_RECOMMENDED`), while preserving valid OULAD schema/semantics
     and strong learnable signal (`ROC-AUC >= 0.80`, `Precision@Top20% >= 0.65`)
     so the Challenger passes all 3 gates and is promoted.
  3. `new_semester_cohort`:
     Simulates an expanded semester cohort update (+25% student registrations and
     shifted digital engagement patterns), triggering full M1->M2->M3->Drift->M4->
     Evaluate->Release->M5 retraining and updating `active_release.json`.
  4. `corrupted_feed_quarantine`:
     Simulates a broken LMS extractor (e.g. `sum_click` multiplied by `50x` semantic
     unit error) to prove `DriftMonitor` flags `DATA_QUALITY_OR_SEMANTIC_FAILURE`
     and `retrain_pipeline.py` blocks retraining and enters Safe Mode (Lecture 4 Q05/Q12/Q20).
  5. `rejected_challenger_guard`:
     Simulates a cohort with noisy/inverted label-feature relationship (or evaluated
     against a strict quality threshold) where the Challenger fails `MLGate` and proves
     the pipeline rejects the Challenger and retains the incumbent Champion.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from learnguard.data.schema import (
    ACTIVITY_TYPES,
    AGE_BANDS,
    CODE_PRESENTATIONS,
    HIGHEST_EDUCATION,
    IMD_BANDS,
    REGIONS,
)

SCENARIOS: tuple[str, ...] = (
    "baseline_no_drift",
    "gradual_covariate_drift",
    "new_semester_cohort",
    "corrupted_feed_quarantine",
    "rejected_challenger_guard",
)


@dataclass(frozen=True)
class SimulationResult:
    scenario: str
    output_dir: Path
    total_students: int
    split_counts: dict[str, int]
    expected_drift_decision: str
    expected_pipeline_outcome: str


def generate_oulad_dataset(
    output_dir: Path | str,
    scenario: str = "baseline_no_drift",
    *,
    students_per_presentation: int = 260,
    seed: int = 42,
) -> SimulationResult:
    """Generate a complete 7-CSV OULAD directory for the specified scenario."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown_simulation_scenario:{scenario}:allowed={','.join(SCENARIOS)}")

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    # Expand cohort size for new_semester_cohort
    n_per_pres = (
        int(students_per_presentation * 1.25)
        if scenario == "new_semester_cohort"
        else int(students_per_presentation)
    )

    modules = ("AAA", "BBB", "CCC", "DDD")
    presentations = CODE_PRESENTATIONS  # ("2013B", "2013J", "2014B", "2014J")

    # 1. courses.csv
    courses_rows = []
    for mod in modules:
        for pres in presentations:
            courses_rows.append({
                "code_module": mod,
                "code_presentation": pres,
                "module_presentation_length": 260 if pres.endswith("J") else 240,
            })
    courses_df = pd.DataFrame(courses_rows)

    # 2. assessments.csv (3 early TMAs before cutoff day 27 + 1 late TMA + 1 dateless Exam)
    assessments_rows = []
    assessment_id = 100
    early_assessments_by_mp: dict[tuple[str, str], list[int]] = {}
    for mod in modules:
        for pres in presentations:
            early_ids: list[int] = []
            for day, weight in ((12.0, 20.0), (19.0, 30.0), (25.0, 50.0)):
                assessment_id += 1
                early_ids.append(assessment_id)
                assessments_rows.append({
                    "id_assessment": assessment_id,
                    "code_module": mod,
                    "code_presentation": pres,
                    "assessment_type": "TMA",
                    "date": day,
                    "weight": weight,
                })
            early_assessments_by_mp[(mod, pres)] = early_ids
            # Late TMA after cutoff (day 60)
            assessment_id += 1
            assessments_rows.append({
                "id_assessment": assessment_id,
                "code_module": mod,
                "code_presentation": pres,
                "assessment_type": "TMA",
                "date": 60.0,
                "weight": 50.0,
            })
            # Dateless final Exam
            assessment_id += 1
            assessments_rows.append({
                "id_assessment": assessment_id,
                "code_module": mod,
                "code_presentation": pres,
                "assessment_type": "Exam",
                "date": np.nan,
                "weight": 100.0,
            })
    assessments_df = pd.DataFrame(assessments_rows)

    # 3. vle.csv
    vle_rows = []
    site_id = 1000
    sites_by_mp: dict[tuple[str, str], list[int]] = {}
    for mod in modules:
        for pres in presentations:
            mp_sites: list[int] = []
            for act_idx in range(4):
                site_id += 1
                mp_sites.append(site_id)
                vle_rows.append({
                    "id_site": site_id,
                    "code_module": mod,
                    "code_presentation": pres,
                    "activity_type": ACTIVITY_TYPES[act_idx % len(ACTIVITY_TYPES)],
                    "week_from": float(act_idx + 1),
                    "week_to": float(act_idx + 2),
                })
            sites_by_mp[(mod, pres)] = mp_sites
    vle_df = pd.DataFrame(vle_rows)

    # Scenario distribution parameters
    is_shifted = scenario in {
        "gradual_covariate_drift",
        "new_semester_cohort",
        "rejected_challenger_guard",
    }
    is_corrupted = scenario == "corrupted_feed_quarantine"
    is_noisy_challenger = scenario == "rejected_challenger_guard"

    student_info_rows = []
    student_reg_rows = []
    student_asm_rows = []
    student_vle_rows = []

    student_id_counter = 10000
    split_counts = {"train": 0, "validation": 0, "holdout": 0}

    for pres in presentations:
        split_name = (
            "train"
            if pres in ("2013B", "2013J")
            else ("validation" if pres == "2014B" else "holdout")
        )
        for idx in range(n_per_pres):
            student_id_counter += 1
            sid = student_id_counter
            mod = modules[idx % len(modules)]
            gender = "M" if (idx % 2 == 0) else "F"

            if is_shifted:
                region = REGIONS[(idx + 5) % 4]  # concentrated regional shift
                studied_credits = int(rng.choice([90, 120, 150], p=[0.45, 0.40, 0.15]))
                prev_attempts = int(rng.choice([0, 1, 2], p=[0.65, 0.25, 0.10]))
            else:
                region = REGIONS[idx % len(REGIONS)]
                studied_credits = int(rng.choice([60, 90, 120], p=[0.70, 0.20, 0.10]))
                prev_attempts = int(rng.choice([0, 1, 2], p=[0.82, 0.14, 0.04]))

            edu = HIGHEST_EDUCATION[idx % len(HIGHEST_EDUCATION)]
            imd = None if (idx % 25 == 0) else IMD_BANDS[idx % len(IMD_BANDS)]
            age = AGE_BANDS[idx % len(AGE_BANDS)]
            disability = "Y" if (idx % 12 == 0) else "N"

            # Latent student academic engagement ability z in [-2.5, +2.5]
            z = float(rng.normal(0.15 if is_shifted else 0.0, 1.15))
            # Make ~3% of students insufficient_data (0 clicks, 0 submissions)
            is_inactive = (idx % 33 == 0)

            if is_inactive:
                w12_clicks = 0
                w34_clicks = 0
                n_subs = 0
                avg_score = np.nan
            else:
                # Engaged students (z > 0) have high clicks and positive w34 trend
                if is_shifted:
                    # Higher overall digital VLE click volume & shifted score distribution
                    base_w12 = max(1, int(np.round(115.0 + 55.0 * z + rng.normal(0, 12))))
                    base_w34 = max(1, int(np.round(165.0 + 85.0 * z + rng.normal(0, 15))))
                    score_center = 72.0 + 16.0 * z
                else:
                    base_w12 = max(1, int(np.round(45.0 + 25.0 * z + rng.normal(0, 8))))
                    base_w34 = max(1, int(np.round(55.0 + 35.0 * z + rng.normal(0, 10))))
                    score_center = 63.0 + 18.0 * z

                if is_corrupted:
                    # Semantic unit explosion: LMS heartbeat bug multiplies sum_click by 50x!
                    base_w12 = min(6900, base_w12 * 50)
                    base_w34 = min(6900, base_w34 * 50)

                w12_clicks = max(1, min(6900, base_w12))
                w34_clicks = max(1, min(6900, base_w34))

                if z > 0.4:
                    n_subs = 3
                elif z > -0.4:
                    n_subs = 2
                elif z > -1.1:
                    n_subs = 1
                else:
                    n_subs = 0

                avg_score = float(np.clip(score_center + rng.normal(0, 5.0), 5.0, 99.0))

            # Determine final_result (Pass/Distinction -> label 0; Fail/Withdrawn -> label 1)
            total_clicks = w12_clicks + w34_clicks
            score_signal = (avg_score - 60.0) / 20.0 if not np.isnan(avg_score) else -1.2
            click_signal = (np.log1p(total_clicks) - 4.5) * 1.1
            sub_signal = (n_subs - 1.5) * 0.7
            risk_logit = -(1.4 * score_signal + 1.1 * click_signal + 0.8 * sub_signal) + 0.35 * prev_attempts
            risk_prob = 1.0 / (1.0 + np.exp(-np.clip(risk_logit, -8.0, 8.0)))

            if is_noisy_challenger:
                # Corrupt label signal so Challenger model has poor ROC-AUC (< 0.58)
                at_risk = bool(rng.random() < 0.48)
            else:
                noise = float(rng.uniform(-0.08, 0.08))
                at_risk = bool((risk_prob + noise) >= 0.50)

            if at_risk:
                final_result = "Withdrawn" if (idx % 3 == 0) else "Fail"
            else:
                final_result = "Distinction" if (z > 1.2) else "Pass"

            student_info_rows.append({
                "code_module": mod,
                "code_presentation": pres,
                "id_student": sid,
                "gender": gender,
                "region": region,
                "highest_education": edu,
                "imd_band": imd,
                "age_band": age,
                "num_of_prev_attempts": prev_attempts,
                "studied_credits": studied_credits,
                "disability": disability,
                "final_result": final_result,
            })

            # Registration before cutoff; withdrawn students who stayed past cutoff withdraw at day 90
            student_reg_rows.append({
                "code_module": mod,
                "code_presentation": pres,
                "id_student": sid,
                "date_registration": float(-25 + (idx % 20)),
                "date_unregistration": 95.0 if final_result == "Withdrawn" else np.nan,
            })

            mp_sites = sites_by_mp[(mod, pres)]
            if not is_inactive:
                # Week 1-2 clicks (days 2 and 9)
                c1 = max(1, w12_clicks // 2)
                c2 = max(1, w12_clicks - c1)
                student_vle_rows.append({
                    "code_module": mod,
                    "code_presentation": pres,
                    "id_student": sid,
                    "id_site": mp_sites[0],
                    "date": 3,
                    "sum_click": int(c1),
                })
                student_vle_rows.append({
                    "code_module": mod,
                    "code_presentation": pres,
                    "id_student": sid,
                    "id_site": mp_sites[1],
                    "date": 10,
                    "sum_click": int(c2),
                })
                # Week 3-4 clicks (days 16 and 23)
                c3 = max(1, w34_clicks // 2)
                c4 = max(1, w34_clicks - c3)
                student_vle_rows.append({
                    "code_module": mod,
                    "code_presentation": pres,
                    "id_student": sid,
                    "id_site": mp_sites[2],
                    "date": 16,
                    "sum_click": int(c3),
                })
                student_vle_rows.append({
                    "code_module": mod,
                    "code_presentation": pres,
                    "id_student": sid,
                    "id_site": mp_sites[3],
                    "date": 24,
                    "sum_click": int(c4),
                })

            early_ids = early_assessments_by_mp[(mod, pres)]
            for sub_i in range(n_subs):
                asm_id = early_ids[sub_i]
                indiv_score = float(np.clip(avg_score + (sub_i - 1) * 2.0, 0.0, 100.0))
                student_asm_rows.append({
                    "id_assessment": asm_id,
                    "id_student": sid,
                    "date_submitted": int(10 + sub_i * 7),
                    "is_banked": 0,
                    "score": round(indiv_score, 1),
                })

            split_counts[split_name] += 1

    student_info_df = pd.DataFrame(student_info_rows)
    student_reg_df = pd.DataFrame(student_reg_rows)
    student_asm_df = pd.DataFrame(student_asm_rows)
    student_vle_df = pd.DataFrame(student_vle_rows)

    courses_df.to_csv(out_path / "courses.csv", index=False)
    assessments_df.to_csv(out_path / "assessments.csv", index=False)
    vle_df.to_csv(out_path / "vle.csv", index=False)
    student_info_df.to_csv(out_path / "studentInfo.csv", index=False)
    student_reg_df.to_csv(out_path / "studentRegistration.csv", index=False)
    student_asm_df.to_csv(out_path / "studentAssessment.csv", index=False)
    student_vle_df.to_csv(out_path / "studentVle.csv", index=False)

    expectations = {
        "baseline_no_drift": ("NO_DRIFT", "SCORE_WITH_CHAMPION"),
        "gradual_covariate_drift": ("DRIFT_RETRAIN_RECOMMENDED", "PROMOTE_CHALLENGER"),
        "new_semester_cohort": ("DRIFT_RETRAIN_RECOMMENDED", "PROMOTE_CHALLENGER"),
        "corrupted_feed_quarantine": (
            "DATA_QUALITY_OR_SEMANTIC_FAILURE",
            "QUARANTINE_AND_SAFE_MODE",
        ),
        "rejected_challenger_guard": (
            "DRIFT_RETRAIN_RECOMMENDED",
            "REJECT_CHALLENGER_KEEP_CHAMPION",
        ),
    }
    exp_decision, exp_outcome = expectations[scenario]

    return SimulationResult(
        scenario=scenario,
        output_dir=out_path,
        total_students=len(student_info_df),
        split_counts=split_counts,
        expected_drift_decision=exp_decision,
        expected_pipeline_outcome=exp_outcome,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LearnGuard MLOps Controlled Data Drift & Cohort Simulator"
    )
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="baseline_no_drift",
        help="Simulation scenario name",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Target directory for the 7 OULAD CSV files",
    )
    parser.add_argument(
        "--students-per-presentation",
        type=int,
        default=260,
        help="Number of students per presentation (default 260 >= MIN_PSI_SAMPLE=200)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    args = parser.parse_args(argv)

    result = generate_oulad_dataset(
        args.output_dir,
        args.scenario,
        students_per_presentation=args.students_per_presentation,
        seed=args.seed,
    )
    print(json.dumps(asdict(result), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
