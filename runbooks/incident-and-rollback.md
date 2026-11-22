# Runbook Ứng phó Sự cố, Rollback Ứng dụng/Mô hình & Khôi phục Cơ sở Dữ liệu

> **Phiên bản:** 3.0 (2026-11-23)
> **Tham chiếu:** [ADR-0008](../../docs/adr/0008-cloud-migration-digitalocean-vm.md), [ADR-0009](../../docs/adr/0009-cicd-pipeline-digitalocean-ghcr.md), [ADR-0010](../../docs/adr/0010-drift-detection-and-continual-retraining-pipeline.md).

---

## 1. Phân loại Mức độ Sự cố & Mục tiêu Khôi phục (RTO / RPO)

| Kịch bản Sự cố | Triệu chứng Phát hiện | Cơ chế Phòng vệ Tự động | Công cụ Khôi phục Thủ công | RTO Mục tiêu |
| :--- | :--- | :--- | :--- | :--- |
| **1. Lỗi Bản dựng Ứng dụng Mới (`api` / `frontend`)** | Healthcheck timeout hoặc `smoke-test.sh` trả mã lỗi `!= 0` sau khi deploy. | `deploy-do.sh` tự động kích hoạt `rollback-do.sh`. | `/opt/learnguard/scripts/cd/rollback-do.sh` | `< 60 giây` |
| **2. Mô hình ML Mới (Challenger) Hoạt động Bất thường** | Tỷ lệ cảnh báo (`realized_alert_rate`) lệch hoặc cố vấn phản hồi chất lượng dự đoán giảm. | Gate 1–3 chặn từ trước khi promote; nếu phát hiện hậu kiểm thì rollback con trỏ release. | `python /opt/learnguard/deploy/ml/retrain_pipeline.py --mode rollback --target-release-id <PREVIOUS_RELEASE_ID> --artifacts-dir /mnt/data/artifacts` | `< 3 phút` |
| **3. Sự cố Dịch vụ LLM Bên ngoài (OpenRouter Timeout / 429 / 5xx)** | Log `llm_calls` ghi nhận lỗi kết nối tới OpenRouter API. | Backend tự động chuyển sang **Ollama local (`qwen2.5:3b`)** hoặc mẫu **`fallback_review`**, không trả HTTP 500. | Bật profile `llm-fallback` (`ollama`) hoặc xoay khóa API | `0 giây` (Graceful Degradation) |
| **4. Lỗi Dữ liệu Đầu vào / Rò rỉ Thời gian (`date > 27`)** | `M1/M3` hoặc `drift_monitor.py` báo `DATA_QUALITY_OR_SEMANTIC_FAILURE`. | Pipeline tự động vào **Safe Mode**: cách ly file lỗi, cấm retrain và giữ nguyên bảng `ml_predictions` hiện tại. | Kiểm tra `/opt/learnguard/data/artifacts/drift-reports/` | `0 giây` (Không làm hỏng dữ liệu) |
| **5. Hỏng hoặc Mất Dữ liệu PostgreSQL** | Lỗi ổ đĩa hoặc thao tác quản trị sai trên DB. | Bản sao lưu tự động hàng ngày (`02:15 UTC`) và trước mỗi lần deploy (`backup-db.sh`). | `/opt/learnguard/scripts/cd/restore-db.sh --file <dump.sql.gz>` | `< 5 phút` (RPO `<= 24h`, trước deploy `RPO = 0`) |

---

## 2. Quy trình 1 — Rollback Ứng dụng Container (`api` & `frontend`)

Trước mỗi lần nâng cấp, `deploy-do.sh` luôn ghi lại chính xác digest `@sha256:...` đang chạy ổn định vào `/opt/learnguard/deploy/digitalocean/last_good_release.env`.

### Thực thi Rollback 1 Lệnh
```bash
ssh lgops@<DROPLET_IP>
/opt/learnguard/scripts/cd/rollback-do.sh --compose-dir /opt/learnguard/deploy/digitalocean
```

### Xác nhận sau Rollback
```bash
/opt/learnguard/scripts/cd/smoke-test.sh --base-url http://127.0.0.1:80
```

---

## 3. Quy trình 2 — Rollback Phiên bản Mô hình ML (`active_release.json`)

Thông tin phiên bản mô hình đang phục vụ (`Champion`) và danh sách các phiên bản trước đó (`rollback_history`) được quản lý nguyên tử tại `/opt/learnguard/data/artifacts/model-releases/active_release.json`.

### Bước 1: Kiểm tra lịch sử các Model Release trên Droplet
```bash
cat /opt/learnguard/data/artifacts/model-releases/active_release.json | jq .
```

### Bước 2: Quay lui về Model Release trước đó và chấm điểm lại bảng `ml_predictions`
```bash
cd /opt/learnguard/deploy/digitalocean
docker compose -f docker-compose.prod.yml --profile batch run --rm ml-worker \
  --mode rollback --target-release-id <PREVIOUS_RELEASE_ID> --artifacts-dir /mnt/data/artifacts
```
Hoặc chạy trực tiếp bằng Python trong container/môi trường ML:
```bash
python /opt/learnguard/deploy/ml/retrain_pipeline.py \
  --mode rollback --target-release-id <PREVIOUS_RELEASE_ID> --artifacts-dir /mnt/data/artifacts
```

Pipeline sẽ tự động:
1. Xác thực chữ ký SHA-256 của gói `model-release.v1` cũ (`verify-release`).
2. Cập nhật nguyên tử `active_release.json` trỏ về release cũ.
3. Chạy lại bước `M5 score` để cập nhật bảng `ml_predictions` bằng đúng mô hình đã khôi phục.

---

## 4. Quy trình 3 — Sao lưu và Khôi phục Cơ sở Dữ liệu PostgreSQL

### 4.1. Tạo bản sao lưu thủ công ngay lập tức
```bash
/opt/learnguard/scripts/cd/backup-db.sh --compose-dir /opt/learnguard/deploy/digitalocean
ls -lh /opt/learnguard/data/backups/
```
Mỗi bản sao lưu bao gồm:
- `learnguard_pg_YYYYMMDDTHHMMSSZ.sql.gz`: File dump nén mức 9.
- `learnguard_pg_YYYYMMDDTHHMMSSZ.sql.gz.sha256`: Mã băm SHA-256 kiểm tra tính toàn vẹn.

### 4.2. Khôi phục từ bản sao lưu (`restore-db.sh`)
```bash
/opt/learnguard/scripts/cd/restore-db.sh \
  --compose-dir /opt/learnguard/deploy/digitalocean \
  --file /opt/learnguard/data/backups/learnguard_pg_<TIMESTAMP>.sql.gz
```
Script `restore-db.sh` tự động:
1. Kiểm tra mã băm `sha256sum --check` để đảm bảo file sao lưu không bị hỏng.
2. Nạp lại toàn bộ cấu trúc bảng và dữ liệu vào container `lg-postgres`.
3. Chạy lại `/docker-entrypoint-initdb.d/10-init-db.sh` để khôi phục quyền phân tách tối thiểu (`lg_ml_writer` sở hữu `ml_predictions`; `lg_api` chỉ có quyền `SELECT` trên `ml_predictions` và CRUD trên các bảng backend).

---

## 5. Quy trình 4 — Xử lý Sự cố Dịch vụ LLM (OpenRouter Outage / Rate-Limit)

Theo quy chuẩn **SPEC-04** (CMU MLIP Lec 1 & Lec 6 — *Graceful Degradation*):
- Khi OpenRouter gặp sự cố hoặc quá thời gian chờ (`LLM_TIMEOUT_SECONDS=30`), Backend tự động chuyển sang:
  1. **Tầng dự phòng 1 (Local LLM Fallback):** Gọi container `lg-ollama` (`ollama/qwen2.5:3b`) trong mạng nội bộ `lg_backend_net`.
  2. **Tầng dự phòng 2 (Deterministic Template Fallback):** Nếu container `ollama` chưa bật hoặc quá tải, Backend tự động sinh bản tóm tắt có cấu trúc từ 3 tín hiệu SHAP hàng đầu (`top_signals_json`) với trạng thái `status = fallback_review` để cố vấn vẫn làm việc bình thường.

Để khởi chạy container `ollama` local trên DigitalOcean Droplet:
```bash
cd /opt/learnguard/deploy/digitalocean
docker compose -f docker-compose.prod.yml --profile llm-fallback up -d ollama
docker exec lg-ollama ollama pull qwen2.5:3b
```
