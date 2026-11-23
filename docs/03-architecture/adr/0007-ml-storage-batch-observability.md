# ADR-0007 — ML storage/batch + Observability

- **Trạng thái:** Accepted
- **Ngày:** 2026-11-04 (sửa 2026-11-04: thêm tùy chọn private endpoint cho Files)

## Bối cảnh
ML batch cần: nguồn CSV (~464MB giải nén), lưu artifacts (ingestion/snapshot/preprocessing/model/prediction-batches) bền vững qua các lần chạy, và ghi kết quả vào PG (private). Cần quan sát API + job.

## Quyết định
- **Azure Files** (`storage_share`) mount vào job container cho `data/oulad/` và `artifacts/` (persistent). Wrapper job `cd` vào mount hoặc truyền path tường minh (xem app-facts.md §2.1).
- **Storage security:** mount bằng **account key / SAS**.
  - **Dev (chốt D-013, rẻ nhất):** **storage firewall + service endpoint** trên `snet-cae` — chặn Internet, không tốn phí private endpoint (~$7/tháng/cái).
  - **Prod:** nâng lên **private endpoint** vào `snet-pe` + private DNS.
  - Cần xác minh khi implement: service endpoint từ subnet của Container Apps Environment có hoạt động đúng không.
- **Container App Job** chạy M1→M5 (trigger manual cho M4 train; cron cho score). Exit code job phản ánh kết quả (0/1/2).
- **Observability:** Log Analytics + Application Insights; API ghi request duration; job ghi log thời lượng từng stage; bảng `llm_calls` ghi usage/cost/latency.

## Hệ quả
- Artifacts model/preprocessing bền vững → score dùng lại model release, không phải train lại mỗi lần.
- Dữ liệu nguồn (CSV) cần đưa lên share 1 lần (hoặc giải nén từ `archive.zip` commit trong repo).
- Job phải VNet-integrated để tới PG private (và Files private nếu bật).

## Cần xác minh
- Cơ chế mount Azure Files vào Container App Job (volume mount bằng account key/SAS) + giới hạn size share.
- Chi phí Azure Files + private endpoint (P0.6).
