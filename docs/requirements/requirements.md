# LearnGuard — Requirements (hạ tầng & phi chức năng)

> File "kiến thức" → không commit. Tổng hợp yêu cầu dẫn xuất kiến trúc.
> Nguồn: đề bài (FR-08, FR-09, performance, privacy, budget), AGENT.md §3, đối chiếu code (app-facts.md).

## 1. Reliability (FR-08)

| Yêu cầu | Dẫn xuất kiến trúc |
|---|---|
| ML fail → trạng thái lỗi tường minh, KHÔNG score | Job exit code != 0; M3 gates chặn; không deploy "vượt gate" |
| LLM unavailable → lỗi tường minh, không mất dữ liệu | Fallback model (Ollama) + retry (tenacity) + ghi `llm_calls.status`; brief vẫn tạo version |
| Thiếu dữ liệu → lỗi tường minh | `ml_predictions.status ∈ {insufficient_data, no_prediction}` (đã có); job fail nếu thiếu CSV |
| Không mất dữ liệu | `ml_predictions` upsert all-or-nothing; DB transaction; Azure Files persistent cho artifacts |

## 2. Traceability & Audit (FR-09)

- Lưu version model/data/config/prediction/thao tác advisor/lỗi → audit + traceability.
- Đã có trong schema: `run_id`, `model_version`, `snapshot_version`, `cutoff_day`, `scored_at` (ml_predictions); `audit_logs` append-only; `briefs`/`decisions` append-only.
- Hạ tầng: Log Analytics + App Insights thu metrics/log; `llm_calls` ghi usage/cost/latency (không log prompt/response).

## 3. Performance & Cost

| Yêu cầu | Dẫn xuất |
|---|---|
| Đo p50/p95 latency tạo brief + chi phí LLM | App Insights (request duration) + bảng `llm_calls` (cost_usd, latency_ms) |
| Đo thời gian xử lý data + dự báo | Log thời lượng job M1→M5 (Job execution time) |
| Rẻ + scale-to-zero | Container Apps consumption; Job chỉ chạy định kỳ; SWA free/standard; PG Flexible SKU nhỏ; LLM free-tier |

## 4. Privacy

- Data minimization: chỉ `student_key` (hash 16 hex), không `id_student`/PII trong DB backend; không log PII/secrets.
- Kiểm soát truy cập: (đang thiếu) auth M6 chưa có → **app-change-request bắt buộc** trước khi expose prod.
- Bảo vệ logs: không ghi prompt/response LLM, không ghi DSN/key.
- Hạn chế thông tin gửi LLM: backend chỉ gửi context tối thiểu (backend tự lo).

## 5. Security & Ràng buộc Azure (bắt buộc)

- KHÔNG RBAC role-assignment, KHÔNG `Microsoft.Network` (VNet/NSG/private endpoint/private DNS/AppGw/FrontDoor).
- → Data-plane auth duy nhất: Key Vault **access policy** (không RBAC), ACR **repo-scoped token/admin user**, Storage **account key/SAS**, PostgreSQL **public + TLS + firewall**, Container Apps **ingress IP restriction**.
- Least-privilege chỉ ở data-plane: tách 2 DB user `lg_ml_writer` (INSERT/UPDATE/SELECT trên ml_predictions) và `lg_api` (SELECT) — làm ở tầng PG, không cần Azure RBAC.
- CI: UAMI + OIDC (không lưu secret); nhưng gán role cho UAMI **cần Admin** → ticket (xem admin-requests.md).

## 6. Yêu cầu công cụ (đã chốt)

- IaC = **Terraform** (`hashicorp/azurerm`).
- CI/CD = GitHub Actions + OIDC; immutable image theo digest; release manifest (gitops); blue/green + rollback.
- Cấm trong IaC: `Microsoft.Authorization/roleAssignments`, `Microsoft.Network/*` (guardrail fail build).

## 7. Tiêu chí chấp nhận (Definition of Done cho hạ tầng)

1. `terraform plan` sạch, không chứa resource type bị cấm (guardrail pass).
2. API/Job chạy từ image theo digest (không tag động).
3. Deploy blue/green + rollback có runbook + lệnh kiểm chứng.
4. Secret tập trung Key Vault, không in/log/commit.
5. Observability: App Insights + Log Analytics + alert cơ bản.
6. prod có approval gate trong workflow.
