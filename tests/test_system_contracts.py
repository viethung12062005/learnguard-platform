"""Cross-boundary System & Semantic Contract Tests (`test_system_contracts.py`).

Implements CMU MLIP Lecture 6 ("Green components, red system" & "Silent success"
prevention) across `Data-ML-MLOPS`, `BE-MLOPS`, and `learnguard-platform`:
  1. Verifies `student_key` SHA-256 formula & test vector parity between
     `learnguard.ml.scoring._pseudonymous_key` and
     `learnguard_backend.services.student_keys.pseudonymous_key`.
  2. Verifies `prediction-batch.v1` 15-column Parquet output matches
     `learnguard_backend.db.models.MLPredictionRecord`, 4-status domain
     (`PREDICTION_STATUSES`), and JSON serialization (`top_signals_json`, `features_json`)
     without silent NaNs or PII leakage.
  3. Verifies `eval-report.v1` scorecards (`eval_data.json`, `eval_ml.json`,
     `eval_behavioral.json`) published by `retrain_pipeline.py` / `behavioral_gate.py`
     are loaded and served by `learnguard_backend.api.app.create_app` via FastAPI
     `TestClient` (`GET /evaluations` and `GET /evaluations/{run_id}`).
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient
from learnguard.ml.scoring import (
    PREDICTION_COLUMNS,
    STATS_FEATURE_COLUMNS,
    PredictionStatus,
)
from learnguard.ml.scoring import (
    _pseudonymous_key as ml_pseudonymous_key,
)
from learnguard_backend.api.app import _parse_features, _parse_top_signals, create_app
from learnguard_backend.db.entities import PREDICTION_STATUSES
from learnguard_backend.db.models import MLPredictionRecord
from learnguard_backend.services.student_keys import (
    TEST_VECTORS,
)
from learnguard_backend.services.student_keys import (
    pseudonymous_key as be_pseudonymous_key,
)
from learnguard_backend.settings import BackendSettings

from deploy.ml.data_simulator import generate_oulad_dataset
from deploy.ml.retrain_pipeline import run_continual_pipeline


def test_student_key_contract_parity_between_ml_and_backend() -> None:
    """Verify ML and Backend compute identical 16-hex student_key across canonical & synthetic vectors."""
    for mod, pres, sid, expected in TEST_VECTORS:
        ml_key = ml_pseudonymous_key(mod, pres, sid)
        be_key = be_pseudonymous_key(mod, pres, sid)
        assert ml_key == expected
        assert be_key == expected
        assert ml_key == be_key

    for mod in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"):
        for pres in ("2013B", "2013J", "2014B", "2014J"):
            for sid in (1, 42, 11391, 999999):
                assert ml_pseudonymous_key(mod, pres, sid) == be_pseudonymous_key(
                    mod, pres, sid
                )


def test_prediction_batch_and_evaluation_contract_with_fastapi_backend(
    tmp_path: Path,
) -> None:
    """Run pipeline to produce prediction-batch.v1 & eval-report.v1 and verify Backend consumption."""
    raw_dir = tmp_path / "oulad_raw"
    artifacts_dir = tmp_path / "artifacts"
    generate_oulad_dataset(
        raw_dir, "baseline_no_drift", students_per_presentation=210, seed=42
    )

    run_id = "contract-run-01"
    exit_code, report = run_continual_pipeline(
        raw_dir, artifacts_dir, mode="auto", run_id=run_id
    )
    assert exit_code == 0
    assert report.prediction_batch_dir is not None
    assert report.evaluation_dir is not None

    # 1. Verify prediction-batch.v1 schema vs BE-MLOPS MLPredictionRecord
    predictions_path = Path(report.prediction_batch_dir) / "predictions.parquet"
    df = pd.read_parquet(predictions_path)
    assert tuple(df.columns) == PREDICTION_COLUMNS
    assert "id_student" not in df.columns  # PII guard

    be_record_fields = {f.name for f in fields(MLPredictionRecord)}
    # Every column in prediction-batch.v1 must exist on MLPredictionRecord
    for col in PREDICTION_COLUMNS:
        assert col in be_record_fields, f"Column {col} missing from BE MLPredictionRecord"

    # Verify status domain parity
    ml_statuses = {st.value for st in PredictionStatus}
    assert ml_statuses == set(PREDICTION_STATUSES)
    assert set(df["status"].unique()) <= set(PREDICTION_STATUSES)

    # Verify insufficient_data rows strictly have NULL predicted_label
    insuff_rows = df[df["status"] == PredictionStatus.INSUFFICIENT_DATA.value]
    assert len(insuff_rows) > 0
    assert insuff_rows["predicted_label"].isna().all()

    # Verify backend parsers handle top_signals_json and features_json cleanly without demographic PII
    forbidden_demographics = {
        "gender",
        "region",
        "highest_education",
        "imd_band",
        "age_band",
        "disability",
    }
    for row in df.head(25).to_dict(orient="records"):
        signals = _parse_top_signals(row["top_signals_json"])
        assert len(signals) > 0
        for sig in signals:
            assert sig.direction in {"increases_risk", "decreases_risk", "neutral"}
        feats = _parse_features(row["features_json"])
        assert set(feats.keys()) == set(STATS_FEATURE_COLUMNS)
        assert not (set(feats.keys()) & forbidden_demographics)

    # 2. Verify BE-MLOPS FastAPI /evaluations endpoints serve all 3 scorecards (data, ml, behavioral)
    settings = BackendSettings(
        database_url="",
        jwt_secret="test-secret-contract-check",
        evaluations_dir=str(artifacts_dir / "evaluations"),
        oulad_data_dir=str(raw_dir),
    )
    app = create_app(settings=settings)
    client = TestClient(app)

    resp_list = client.get("/evaluations")
    assert resp_list.status_code == 200
    payload_list = resp_list.json()
    assert payload_list["total"] == 1
    run_summary = payload_list["runs"][0]
    assert run_summary["run_id"] == run_id
    assert set(run_summary["subjects"]) == {"data", "ml", "behavioral"}
    assert run_summary["overall_status"] in {"pass", "warn"}
    assert "eval_behavioral.json" in run_summary["reports_available"]

    resp_detail = client.get(f"/evaluations/{run_id}")
    assert resp_detail.status_code == 200
    payload_detail = resp_detail.json()
    assert payload_detail["run_id"] == run_id
    assert set(payload_detail["reports"].keys()) == {"data", "ml", "behavioral"}
    behav_report = payload_detail["reports"]["behavioral"]
    assert behav_report["schema_version"] == "eval-report.v1"
    assert behav_report["summary"]["total"] == 6
    assert behav_report["summary"]["fail"] == 0
