# LearnGuard — Active Cloud Option B: DigitalOcean VM & CI/CD Target Architecture (v3)

> **Phiên bản:** 3.1 (2026-11-23)
> **Trạng thái:** **Accepted — Active Cloud Option B (DigitalOcean VM)**
> **Quan hệ Dual-Cloud:** Hoạt động song song như **Option B** bên cạnh **Option A ([Azure PaaS v2](azure-target-architecture.md))** theo chiến lược **Cloud-Portable Dual-Option (Deploy-Where-Available)** ([`dual-cloud-strategy.md`](dual-cloud-strategy.md)). Operator triển khai lên DigitalOcean **hoặc** Azure tùy theo credit/tài khoản khả dụng tại thời điểm vận hành — không cần chạy hay trả phí đồng thời cả hai cloud.
> **Tham chiếu ADR:** [ADR-0008](adr/0008-cloud-migration-digitalocean-vm.md) · [ADR-0009](adr/0009-cicd-pipeline-digitalocean-ghcr.md) · [ADR-0010](adr/0010-drift-detection-and-continual-retraining-pipeline.md)

---

## 1. Mục tiêu Kiến trúc & Ràng buộc Vận hành (Option B — DigitalOcean VM)

1. **Production-Like trên DigitalOcean Droplet VM:**
   - Triển khai toàn bộ hệ thống LearnGuard trên **DigitalOcean Droplet** (Ubuntu 24.04 LTS, mặc định `s-4vcpu-8gb` hoặc tối thiểu `s-2vcpu-4gb`) nằm trong **DigitalOcean VPC (`10.116.0.0/20`)**, được bảo vệ bởi **DigitalOcean Cloud Firewall** + host `ufw` + `fail2ban`.
   - Phân tách mạng container trong `deploy/digitalocean/docker-compose.prod.yml` thành 2 vùng cô lập:
     - `lg_frontend_net` (DMZ): chứa `frontend` (Nginx) và `api` (FastAPI) (+ `ollama` nếu bật profile `llm-fallback`).
     - `lg_backend_net` (`internal: true` — Private Data Plane): chứa `api`, `postgres`, `ml-worker`, `ollama` (optional), `prometheus` / `node-exporter` / `cadvisor`. **PostgreSQL hoàn toàn không mở cổng `5432` ra ngoài host hay Internet.**
2. **Bảo mật Dữ liệu & Least-Privilege ở Tầng Database (Parity với Option A):**
   - Duy trì phân tách 2 role PostgreSQL riêng biệt thông qua `deploy/digitalocean/init-db.sh` & `deploy/db/roles.sql`:
     - `lg_ml_writer`: chỉ sở hữu và có quyền ghi/upsert trên bảng `ml_predictions`.
     - `lg_api`: chỉ có quyền `SELECT` trên `ml_predictions` và quyền CRUD trên các bảng nghiệp vụ backend (`users`, `briefs`, `decisions`, `llm_calls`, `audit_logs`, `chat_sessions`, `chat_messages`), tự động nhận quyền bảng mới do `db-migrate` (`alembic upgrade head`) tạo qua `ALTER DEFAULT PRIVILEGES`.
3. **CI/CD Tự động Hóa Đầu-Cuối trên GitHub-Hosted Runners & Rollback Tức thì:**
   - Mọi thay đổi đi qua GitHub Actions: `Lint & Guardrails → 6-Layer Testing (Unit + Contract + Behavioral + Drift Simulation) → Build Immutable Docker Images → Trivy Scan (exit-code: 1) → Push GHCR (@sha256 digest) → Deploy via SSH → DB Migration → E2E Smoke Test → Auto-Rollback on Failure (< 60s)`.
4. **Đóng Vòng lặp Telemetry, Phát hiện Drift & Continual Retraining:**
   - Chia sẻ Block Storage Volume `/opt/learnguard/data` (`oulad/` + `artifacts/`) giữa `ml-worker` (Read-Write) và `api` (Read-Only) để cố vấn và quản trị viên theo dõi trực tiếp Scorecard đánh giá (`GET /evaluations`) và hành vi 4 tuần (`GET /predictions/.../activity`) trên giao diện web.

---

## 2. Sơ đồ Kiến trúc C4 — Container & Network Topology trên DigitalOcean

```mermaid
flowchart TB
    subgraph USERS["Người dùng & Dịch vụ Ngoài"]
        ADV["Advisor / Giảng viên (Browser)"]
        ADM["Admin / MLOps (Browser / SSH)"]
        GH["GitHub Actions CI/CD + GHCR (ghcr.io/viethung12062005/*)"]
        OR["OpenRouter API (Primary LLM)"]
    end

    subgraph DO_CLOUD["DigitalOcean Cloud — VPC 10.116.0.0/20 (sgp1)"]
        FW["DigitalOcean Cloud Firewall + UFW + Fail2ban\n(Allow 80/443 Public; Allow 22 allowed_ssh_cidrs; Deny 5432/8000/9090 Public)"]

        subgraph DROPLET["DigitalOcean Droplet VM (Ubuntu 24.04 LTS) — /opt/learnguard"]
            subgraph FE_NET["Docker Network: lg_frontend_net (DMZ)"]
                NGINX["Container: lg-frontend (Nginx + React SPA)\nPorts: 80/443 | Rate-Limit 20r/s | 5 Security Headers\n/ -> Static SPA | /api/* -> api:8000"]
            end

            subgraph BE_NET["Docker Network: lg_backend_net (Private Data Plane — internal: true)"]
                API["Container: lg-api (FastAPI / Uvicorn)\nPort 8000 (internal only)\nRole: lg_api (SELECT ml_predictions, CRUD briefs/chat/audit)"]
                PG[("Container: lg-postgres (PostgreSQL 16)\nPort 5432 (internal only)\nVolume: lg_pg_data + daily pg_dump backups")]
                ML["Container: lg-ml-worker (retrain_pipeline.py)\nTriggered by systemd timer / manual / CI\nRole: lg_ml_writer (UPSERT ml_predictions)"]
                OLLAMA["Container: lg-ollama (Profile: llm-fallback)\nqwen2.5:3b | Port 11434 (internal)"]
                OBS["Observability Stack (Profile: observability)\nPrometheus + Node Exporter + cAdvisor"]
            end

            subgraph VOLUMES["DigitalOcean Block Storage 50 GiB (/opt/learnguard/data)"]
                V_OULAD[("oulad/ (7 Raw CSVs & Incoming Extracts)")]
                V_ART[("artifacts/\n- feature_snapshot_m2/\n- model-releases/ (active_release.json)\n- prediction-batches/\n- evaluations/ (eval-report.v1)\n- drift-reports/ (drift-report.v1)")]
                V_BAK[("backups/ (.sql.gz + .sha256 PG Dumps)")]
            end
        end
    end

    ADV -->|HTTPS 443 / HTTP 80| FW --> NGINX
    ADM -->|HTTPS 443 / SSH 22| FW
    GH -->|SSH Deploy + Pull @sha256| FW
    NGINX -->|Reverse Proxy /api/| API
    API -->|"SQL (lg_api)"| PG
    API -->|Fallback LLM| OLLAMA
    API -->|"Primary LLM (HTTPS)"| OR
    API -->|Read-Only Mount| V_ART
    API -->|Read-Only Mount| V_OULAD
    ML -->|Read/Write Mount| V_OULAD
    ML -->|Read/Write Mount| V_ART
    ML -->|"SQL UPSERT (lg_ml_writer)"| PG
    PG -->|backup-db.sh| V_BAK
    OBS -->|Scrape Host & Containers| API
    OBS -->|Scrape Host & Containers| PG
```

---

## 3. Luồng Triển khai CI/CD & Tự động Rollback (Sequence Diagram)

```mermaid
sequenceDiagram
    autonumber
    participant Dev as Engineer / PR
    participant GHA as GitHub Actions CI/CD
    participant GHCR as GHCR (ghcr.io/viethung12062005/*)
    participant DO as DigitalOcean VM (lgops)
    participant Stack as Docker Compose Prod Stack

    Dev->>GHA: Push / Merge to main (or workflow_dispatch)
    GHA->>GHA: Stage 1 (ci-platform.yml): ShellCheck, Ruff, YAML & Compose Validate
    GHA->>GHA: Stage 2 (ci-platform.yml): Unit + Contract + Behavioral (MFT/INV/DIR) + Drift/Retrain Tests
    GHA->>GHCR: Stage 3 (ci-build-and-scan.yml): Build 3 images, Trivy Scan (exit-code 1), Push @sha256
    GHA->>DO: Stage 4 (cd-digitalocean-prod.yml): Sync deploy/ & scripts/ via SSH (GitHub Env: production)
    DO->>DO: Save current running digests to last_good_release.env
    DO->>Stack: Run backup-db.sh (pre-deploy pg_dump + sha256)
    DO->>Stack: Pull @sha256 images & Run init-db.sh + db-migrate (alembic upgrade head)
    DO->>Stack: Rolling update lg-api & lg-frontend with new @sha256 digests
    DO->>Stack: Wait for container healthchecks (/health -> database: reachable)
    DO->>Stack: Run smoke-test.sh (API endpoints, SPA fallback, Security Headers)
    alt Smoke Test PASS
        DO-->>GHA: Deployment Succeeded (record provenance in release manifest)
    else Smoke Test FAIL
        DO->>Stack: Auto-trigger rollback-do.sh (restore last_good_release.env digests)
        DO->>Stack: Re-verify healthcheck of rolled-back containers
        DO-->>GHA: Exit non-zero with failure diagnostics & rollback confirmation
    end
```

---

## 4. Luồng Phát hiện Data Drift, Chẩn đoán & Continual Retraining (Sequence Diagram)

Tuân thủ chặt chẽ nguyên tắc của **Lecture 4 (Q19–Q22)** và **Lecture 5–6** (xem thêm [`drift-and-retraining-specification.md`](drift-and-retraining-specification.md) & [`../../runbooks/drift-and-retraining-runbook.md`](../../runbooks/drift-and-retraining-runbook.md)):
- Không tự động retrain mù quáng khi luồng dữ liệu bị lỗi schema hoặc lỗi ngữ nghĩa (semantic corruption) hoặc khi tuần 4 chưa có nhãn kết quả cuối kỳ (`ASM-03`).
- Chỉ promote mô hình Challenger khi vượt qua toàn bộ cổng kiểm định **Data Gate + ML Gate (Champion vs. Challenger, fail-closed) + Behavioral Gate (MFT/INV/DIR)**.

```mermaid
sequenceDiagram
    autonumber
    participant Cron as Scheduler / Simulator / CI
    participant Orch as Retrain Pipeline (retrain_pipeline.py)
    participant M13 as M1 Ingest -> M2 Snapshot -> M3 Audit
    participant Drift as Drift Monitor (drift_monitor.py)
    participant M4 as M4 Trainer (Challenger)
    participant Gates as Multi-Gate Evaluator (Data + ML + Behavioral)
    participant Reg as Release Registry (active_release.json)
    participant M5 as M5 Batch Scorer & PostgreSQL

    Cron->>Orch: Trigger pipeline (new LMS extract or simulated drift scenario)
    Orch->>M13: Run M1 ingestion + M2 snapshot (cutoff=27) + M3 LeakageAuditor
    alt M1/M3 Hard Failure (Schema / Future Leakage / Corruption)
        M13-->>Orch: FAIL (quarantine bad rows, block pipeline)
        Orch-->>Cron: Enter SAFE MODE (keep Champion & existing DB predictions, emit alert)
    else M1/M3 PASS
        Orch->>Drift: Compare new snapshot vs baseline snapshot (PSI, KS-test, Missingness, Volume, Slices, ASM-03)
        alt Semantic Anomaly / Extreme Corruption Detected
            Drift-->>Orch: Status = DATA_QUALITY_OR_SEMANTIC_FAILURE
            Orch-->>Cron: Block Retraining & Scoring (Safe Mode + Data Engineer Alert)
        else No Significant Drift or ASM-03 Missing Labels (NO_DRIFT / WARN_MONITOR)
            Drift-->>Orch: Status = NO_DRIFT (or WARN_MONITOR)
            Orch->>Reg: Load current verified Champion Release
            Orch->>M5: Score snapshot with Champion Release & UPSERT ml_predictions
        else Genuine Drift + Labeled Cohort (DRIFT_RETRAIN_RECOMMENDED)
            Drift-->>Orch: Status = DRIFT_RETRAIN_RECOMMENDED (publish drift-report.v1)
            Orch->>M4: Fit train-only Preprocessor + Train Challenger Model (with Linear SHAP)
            Orch->>Gates: Run Gate 1 (Data) + Gate 2 (ML vs Champion Baseline) + Gate 3 (Behavioral MFT/INV/DIR)
            Gates->>Gates: Publish atomic eval-report.v1 scorecards to artifacts/evaluations/<run-id>/
            alt Any Gate FAILS (Challenger worse than Champion or fails Behavioral/Fairness)
                Gates-->>Orch: REJECT Challenger
                Orch->>Reg: Keep incumbent Champion active
                Orch-->>Cron: Exit non-zero & Alert ML Owner (without promoting regression)
            else All Gates PASS
                Gates-->>Orch: PROMOTE Challenger
                Orch->>Reg: Package immutable model-release.v1 & atomically update active_release.json
                Orch->>M5: Score snapshot with NEW Champion Release & UPSERT ml_predictions
            end
        end
    end
```

---

## 5. Cấu trúc Thư mục Chuẩn trên DigitalOcean VM (`/opt/learnguard`)

```text
/opt/learnguard/
├── deploy/
│   ├── digitalocean/
│   │   ├── docker-compose.prod.yml
│   │   ├── docker-compose.staging.yml
│   │   ├── .env                         # chmod 600 (KHÔNG commit)
│   │   ├── last_good_release.env        # tự động lưu trước mỗi lần deploy để rollback
│   │   ├── init-db.sh
│   │   └── prometheus.yml
│   ├── db/
│   │   └── roles.sql
│   ├── docker/
│   │   └── nginx.fe.conf
│   ├── ml/
│   │   ├── ml_pipeline.py
│   │   ├── drift_monitor.py
│   │   ├── behavioral_gate.py
│   │   ├── data_simulator.py
│   │   └── retrain_pipeline.py
│   └── releases/
│       ├── dev.yaml
│       └── prod.yaml                    # GitOps release manifest (@sha256 digests)
├── scripts/
│   ├── cd/
│   │   ├── deploy-do.sh
│   │   ├── smoke-test.sh
│   │   ├── rollback-do.sh
│   │   ├── backup-db.sh
│   │   └── restore-db.sh
│   └── do/
│       └── bootstrap-vm.sh
└── data/                                # Mounted from DO Block Storage Volume (50 GiB)
    ├── oulad/                           # 7 file CSV OULAD chuẩn
    ├── artifacts/
    │   ├── ingestion_m1/
    │   ├── feature_snapshot_m2/
    │   ├── preprocessing-runs/
    │   ├── model-runs/
    │   ├── model-releases/
    │   │   └── active_release.json      # Con trỏ release đang active + lịch sử rollback
    │   ├── prediction-batches/
    │   ├── evaluations/                 # API mount RO phục vụ GET /evaluations
    │   └── drift-reports/               # Báo cáo chẩn đoán drift (drift-report.v1)
    └── backups/                         # Bản sao lưu PostgreSQL định kỳ & trước deploy
```

> Xem hướng dẫn triển khai, vận hành và diễn tập khôi phục Option B tại [`../../runbooks/deploy-digitalocean.md`](../../runbooks/deploy-digitalocean.md), [`../../runbooks/drift-and-retraining-runbook.md`](../../runbooks/drift-and-retraining-runbook.md), [`../../runbooks/incident-and-rollback.md`](../../runbooks/incident-and-rollback.md), và chỉ mục tổng hợp [`../04-devops/runbooks-index.md`](../04-devops/runbooks-index.md).
