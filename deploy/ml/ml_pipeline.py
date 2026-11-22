#!/usr/bin/env python3
"""LearnGuard ML batch — chạy toàn pipeline M1..M5 trong Container App / DigitalOcean Job.

Supports `LEARNGUARD_PIPELINE_MODE=auto|legacy`:
  - `auto` (default when `retrain_pipeline` is used or requested): runs continual
    drift-aware M1 -> M2 -> M3 -> DriftMonitor -> Champion-vs-Challenger Gates -> Release -> M5.
  - `legacy` (default for direct backward-compatible M1..M5 one-shot execution unless
    `LEARNGUARD_PIPELINE_MODE=auto` is set): runs M1..M5 sequentially.

Env:
  LEARNGUARD_DATA_DIR       thư mục chứa 7 CSV OULAD (mặc định /mnt/data/oulad)
  LEARNGUARD_ARTIFACTS_DIR  thư mục artifacts (mặc định /mnt/data/artifacts)
  LEARNGUARD_PG_DSN         DSN ghi ml_predictions (secret pg-dsn-ml)
  LEARNGUARD_RUN_ID         tuỳ chọn; mặc định batch-<UTC timestamp>
  LEARNGUARD_CUTOFF_DAY     mặc định 27
  LEARNGUARD_THRESHOLD      mặc định 0.5
  LEARNGUARD_PIPELINE_MODE  auto | legacy (mặc định legacy để giữ tương thích 100%, hoặc auto)
Exit: 0 ok, 1 gate/audit fail, 2 exception.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path


def _log(msg: str) -> None:
    print(f"[ml-pipeline] {msg}", flush=True)


def run_legacy_pipeline(
    data_dir: Path,
    artifacts: Path,
    run_id: str,
    cutoff_day: int,
    threshold: float,
) -> int:
    artifacts.mkdir(parents=True, exist_ok=True)
    ingestion_dir = artifacts / "ingestion_m1"
    snapshot_path = artifacts / "feature_snapshot_m2" / "snapshot.parquet"
    preprocessing_dir = artifacts / "preprocessing-runs" / run_id
    model_dir = artifacts / "model-runs" / run_id
    batch_dir = artifacts / "prediction-batches" / run_id

    _log(f"run_id={run_id} cutoff={cutoff_day} threshold={threshold} mode=legacy")
    _log(f"data_dir={data_dir} artifacts={artifacts}")

    csvs = sorted(p.name for p in data_dir.glob("*.csv"))
    if len(csvs) < 7:
        _log(f"ERROR missing csv: found {len(csvs)} in {data_dir}: {csvs}")
        return 2

    from learnguard.data.features import build_feature_snapshot
    from learnguard.data.ingestion import ingest_oulad
    from learnguard.data.leakage import LeakageAuditor
    from learnguard.data.quality import validate_snapshot
    from learnguard.ml.preprocessing import build_preprocessing_artifact
    from learnguard.ml.scoring import score_snapshot
    from learnguard.ml.training import train_logistic_baseline

    # M1
    _log("M1 ingestion ...")
    ing = ingest_oulad(data_dir, ingestion_dir)
    _log(f"M1 status={ing.status} rows={sum(ing.row_counts.values())}")
    if ing.status != "ok":
        _log(f"M1 errors={ing.errors}")
        return 1

    # M2
    _log("M2 feature snapshot ...")
    snap = build_feature_snapshot(ingestion_dir, snapshot_path, cutoff_day=cutoff_day)
    _log(f"M2 version={snap.snapshot_version}")

    # M3
    _log("M3 leakage audit + quality gates ...")
    audit = LeakageAuditor().audit_snapshot(snap.snapshot_path, ingestion_dir, cutoff_day)
    gate = validate_snapshot(snap.snapshot_path)
    _log(f"M3 audit={audit.status} gate={gate.status}")
    if audit.status != "ok" or gate.status != "ok":
        _log(f"audit violations={getattr(audit, 'violations', None)} gate errors={gate.errors}")
        return 1

    # M4 preprocessing
    _log("M4 preprocess ...")
    pre = build_preprocessing_artifact(snap.snapshot_path, artifacts, run_id)
    _log(f"M4 preprocessing status={pre.status} version={pre.preprocessor_version}")

    # M4 train
    _log("M4 train logistic ...")
    trained = train_logistic_baseline(snap.snapshot_path, preprocessing_dir, artifacts, run_id)
    _log(f"M4 training status={trained.status} version={trained.model_semantic_version}")

    # M5 score
    _log("M5 score + publish ...")
    output = batch_dir / "predictions.parquet"
    report = score_snapshot(
        snap.snapshot_path,
        model_dir,
        preprocessing_dir,
        output,
        threshold=threshold,
        run_id=run_id,
    )
    _log(f"M5 status={report.status} scored={report.scored_rows} output={report.output_path}")

    # Ghi DB (least-privilege role lg_ml_writer) — dùng cùng logic CLI.
    dsn = os.environ.get("LEARNGUARD_PG_DSN", "")
    if not dsn:
        _log("WARN LEARNGUARD_PG_DSN trống — bỏ qua ghi PostgreSQL")
    if report.status == "ok" and dsn:
        import pandas as pd
        from learnguard.ml.predictions_store import (
            PredictionStore,
            PredictionStoreConfig,
        )

        frame = pd.read_parquet(report.output_path)
        with PredictionStore(PredictionStoreConfig(dsn=dsn, table="ml_predictions")) as store:
            store.ensure_schema()
            written = store.write_predictions(frame, run_id)
            stored = store.count_run(run_id)
        _log(f"DB wrote={written} stored={stored}")
        if stored != written:
            _log("ERROR rowcount mismatch")
            return 2
        report.database_write = "ok"
        report.database_rows = stored

    print(json.dumps(report.__dict__, indent=2, default=str), flush=True)
    return 0 if report.status == "ok" else 1


def main() -> int:
    data_dir = Path(os.environ.get("LEARNGUARD_DATA_DIR", "/mnt/data/oulad"))
    artifacts = Path(os.environ.get("LEARNGUARD_ARTIFACTS_DIR", "/mnt/data/artifacts"))
    run_id = os.environ.get("LEARNGUARD_RUN_ID") or datetime.now(UTC).strftime(
        "batch-%Y%m%dT%H%M%SZ"
    )
    cutoff_day = int(os.environ.get("LEARNGUARD_CUTOFF_DAY", "27"))
    threshold = float(os.environ.get("LEARNGUARD_THRESHOLD", "0.5"))
    pipeline_mode = os.environ.get("LEARNGUARD_PIPELINE_MODE", "legacy").strip().lower()

    if pipeline_mode in {"auto", "detect-only", "force-retrain", "force_retrain"}:
        if pipeline_mode == "force_retrain":
            pipeline_mode = "force-retrain"
        _this_dir = Path(__file__).resolve().parent
        _platform_root = _this_dir.parent.parent
        if str(_platform_root) not in sys.path:
            sys.path.insert(0, str(_platform_root))
        from deploy.ml.retrain_pipeline import run_continual_pipeline

        csvs = sorted(p.name for p in data_dir.glob("*.csv"))
        if len(csvs) < 7:
            _log(f"ERROR missing csv: found {len(csvs)} in {data_dir}: {csvs}")
            return 2
        code, report = run_continual_pipeline(
            data_dir,
            artifacts,
            mode=pipeline_mode,
            run_id=run_id,
            cutoff_day=cutoff_day,
            pg_dsn=os.environ.get("LEARNGUARD_PG_DSN") or None,
        )
        print(json.dumps(asdict(report), indent=2, default=str), flush=True)
        return code

    return run_legacy_pipeline(data_dir, artifacts, run_id, cutoff_day, threshold)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        raise SystemExit(2)
