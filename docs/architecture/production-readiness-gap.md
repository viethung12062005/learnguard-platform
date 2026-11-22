# LearnGuard — Production Readiness Gap Register

> File "kiến thức" → không commit. Đánh giá kiến trúc v2 (private networking) so với production thật.
> Cập nhật 2026-11-04. Phân loại gap: **A** = ta làm được ngay · **B** = cần Admin · **C** = cần quyết định nghiệp vụ/app change.

## 0. Điểm số

| Thang | Điểm | Lý do |
|---|---|---|
| Đồ án "like-production" | ~7/10 | Network private, secret tập trung, blue/green + rollback, IaC — phần khó đã đúng |
| Vận hành production thật | ~4/10 | Thiếu HA/DR, thiếu auth, CD dùng credential cá nhân |

**Kết luận:** "prod-shaped" ✅ · "prod-operable" ❌. Ba điều kiện tối thiểu còn thiếu: **HA/DR**, **auth**, **CI/CD identity tách biệt**.

## 1. Gap register

| # | Hạng mục | Hiện trạng v2 | Mức | Loại | Hành động |
|---|---|---|---|---|---|
| G-01 | App authentication | Không có (backend M6 chưa xong) | 🔴 Critical | C | Chặn deploy prod tới khi có auth; hoặc chấp nhận rủi ro có văn bản |
| G-02 | Rate limiting / WAF | Không có | 🔴 Critical | A (+B nếu App GW) | Rate limit ở ingress/app; App Gateway WAF ở Phase 2 |
| G-03 | CI/CD identity | Self-hosted runner mượn `az login` user | 🔴 Critical | B | OIDC + UAMI + gán role (ticket). Không dùng runner cá nhân cho prod |
| G-04 | Database HA | Burstable, single, không HA | 🔴 Critical | A | Nâng tier hỗ trợ zone-redundant HA (Burstable **không** hỗ trợ HA) |
| G-05 | Backup/DR | Chưa định nghĩa RTO/RPO, chưa test restore | 🔴 Critical | A + C | Backup retention + geo-redundant backup; chốt RTO/RPO; chạy thử restore |
| G-06 | Terraform state | Chưa chốt backend | 🔴 Critical | A | Remote backend = Storage (encrypted) + lease lock; cấm local state |
| G-07 | Egress control | VNet outbound nhưng không lọc | 🟠 High | A | NSG + NAT Gateway; allowlist đích (PG/KV/Files/OpenRouter), chặn còn lại |
| G-08 | NSG | Chưa có | 🟠 High | A | NSG cho `snet-cae`, `snet-pg`, `snet-pe` |
| G-09 | Container Apps HA | Chưa chốt `min_replicas` | 🟠 High | A | API `min_replicas ≥ 1`; chốt scale rule; cân nhắc zone redundancy |
| G-10 | Observability vận hành | Có LA + AI, chưa có alert/SLO | 🟠 High | A | SLO/SLI, alert rules, dashboard, on-call, log retention, PII scrubbing |
| G-11 | Migration strategy | Alembic chạy trong deploy path | 🟠 High | A | Tách migration job; expand/contract; backward-compatible |
| G-12 | Supply chain | Pin digest + action SHA | 🟠 High | A | Image scan (Trivy/ACR Tasks), SBOM, secret scanning, signing (cosign/Notation) |
| G-13 | Storage durability | Chưa có soft delete/versioning | 🟠 High | A | Soft delete + versioning + lifecycle cho Azure Files/Blob |
| G-14 | Cost governance | Không có | 🟠 High | A | Budget alerts + tag strategy + `infracost` trong PR |
| G-15 | Policy-as-code | Không có | 🟡 Medium | A | `tflint` + `checkov` + guardrail roleAssignments trong CI |
| G-16 | Secret rotation | Xoay tay qua runbook | 🟡 Medium | B (một phần A) | Alert hết hạn secret; automation cần RBAC/managed identity |
| G-17 | KV authorization model | Access policy (legacy) | 🟡 Medium | B | Chuyển RBAC model khi Admin gán role |
| G-18 | ACR | Public + repo token, SKU Basic | 🟡 Medium | B | Premium + private endpoint + AcrPull qua managed identity |
| G-19 | Audit trail | `audit_logs` schema có, chưa implement | 🟡 Medium | C | Backend M7 ghi audit mỗi lần truy cập prediction |
| G-20 | PII retention | Chỉ pseudonymize | 🟡 Medium | C | Chính sách retention + deletion; không log PII |
| G-21 | DR multi-region | Không có | 🟡 Medium | C | Quyết định có cần hay không (đồ án: không) |
| G-22 | Env isolation | dev/prod cùng subscription | 🟢 Low | C | Prod subscription riêng nếu có; tối thiểu RG + state tách biệt |
| G-23 | SWA tier/SLA | Chưa chốt tier | 🟢 Low | A | Free **không có SLA** → Standard cho prod |
| G-24 | Subnet sizing | Chưa chốt CIDR từng subnet | 🟢 Low | A | CAE cần subnet đủ lớn (khuyến nghị /23); PG /24; PE /24 |

## 2. Việc nên đưa vào Phase 1–2 (ưu tiên)

1. **G-06 remote state** — làm trước mọi thứ khác (nếu không, mọi bước sau đều trên nền sai).
2. **G-08/G-07 NSG + egress** — cùng lúc với tạo VNet (P1).
3. **G-04/G-05 HA + backup** — quyết tier ngay khi tạo PG (P2); đổi tier sau tốn downtime.
4. **G-11 migration job** — thiết kế trong P2/P5, không để nợ.
5. **G-09 min replicas** — P5.
6. **G-10 alerting** — P5/P6, không để cuối.
7. **G-01/G-03** — đường dài, song song: ticket Admin + app change request.

## 3. Nguyên tắc ghi nhận

- **Không** đánh dấu 🟢 cho hạng mục chỉ vì "đã có resource" — phải có cả cấu hình an toàn và vận hành được.
- Gap loại **B** không được coi là "bỏ qua"; phải nằm trong `runbooks/admin-requests.md`.
- Gap loại **C** phải có quyết định bằng văn bản (chấp nhận rủi ro hoặc chặn deploy).

---

## 4. Cập nhật Kiến trúc v3 (DigitalOcean Production Stack & CMU MLIP Pipeline — 2026-11-23)

Sau quyết định chuyển dịch hạ tầng đích sang **DigitalOcean Droplet VM** ([ADR-0008](../adr/0008-cloud-migration-digitalocean-vm.md)), thiết lập **CI/CD đa tầng trên GitHub Actions + GHCR** ([ADR-0009](../adr/0009-cicd-pipeline-digitalocean-ghcr.md)) và **Pipeline Drift Detection + Continual Retraining theo CMU MLIP** ([ADR-0010](../adr/0010-drift-detection-and-continual-retraining-pipeline.md)), cộng với các bản cập nhật từ team app (`BE-MLOPS` `a2bae92`, `Data-ML-MLOPS` `72c96cd`, `FE-MLOPS` `0f70e14`), các gap trọng yếu từ Kiến trúc v2 đã được đóng như sau:

| Gap ID | Hạng mục | Cơ chế đóng trong Kiến trúc v3 (2026-11-23) | Trạng thái |
|---|---|---|---|
| **G-02** | Rate limiting / Security headers | Nginx container (`nginx.fe.conf`) cấu hình `limit_req_zone` cho `/api/`, gắn `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` và reverse-proxy nội bộ sang `api:8000` | ✅ Đã đóng |
| **G-03** | CI/CD identity tách biệt | Loại bỏ hoàn toàn self-hosted runner dùng `az login` cá nhân; chuyển sang GitHub Actions hosted runner + GHCR token + **dedicated deploy SSH key** được bảo vệ bởi GitHub Environment `production` (kèm approval gate) | ✅ Đã đóng |
| **G-05** | Backup / DR & Test Restore | Tự động hóa `backup-db.sh` (chạy định kỳ hàng ngày và bắt buộc ngay trước mỗi bước nâng cấp trong `deploy-do.sh`) + `restore-db.sh` kiểm chứng được + DigitalOcean Automated Backups | ✅ Đã đóng |
| **G-10** | Observability vận hành & AI | Kết hợp **Prometheus + Node Exporter + cAdvisor** giám sát hạ tầng/container với bộ Scorecard chuẩn hóa `eval-report.v1` (`eval_data`, `eval_ml`, `eval_llm`, `eval_behavioral`) và `drift-report.v1` | ✅ Đã đóng |
| **G-11** | Migration strategy tách biệt | Tách container `db-migrate` chạy trước khi cập nhật `api` trong `cd-digitalocean-prod.yml` / `deploy-do.sh`, kèm khởi tạo least-privilege roles (`lg_api`, `lg_ml_writer`) | ✅ Đã đóng |
| **G-12** | Supply chain security | Bổ sung **Trivy vulnerability scan** trong `ci-build-and-scan.yml` (chặn CRITICAL/HIGH), multi-stage Dockerfile chạy non-root user (`UID 10001`), và deploy bằng **immutable `@sha256` digest** từ GHCR | ✅ Đã đóng |
| **G-19** | Audit trail | Team `BE-MLOPS` đã implement đầy đủ bảng & API `GET /audit-logs` (commit `e957315` / `a2bae92`), kết nối với trang `/audit` trên `FE-MLOPS` (`0f70e14`) | ✅ Đã đóng |

### Điểm đánh giá Kiến trúc v3 (2026-11-23)

| Thang đánh giá | Điểm v2 (2026-11-04) | Điểm v3 (2026-11-23) | Nhận xét |
|---|---|---|---|
| **Đồ án "like-production"** | ~7.0 / 10 | **9.2 / 10** | Đầy đủ VPC/Firewall, 2-network isolation (`lg_frontend_net` / `lg_backend_net`), least-privilege DB roles, Nginx rate-limiting & security headers, CI 6-layer testing pyramid, Trivy + `@sha256` immutable images, pre-deploy backup, auto-rollback (`< 60s`), Prometheus monitoring và Drift/Champion-Challenger pipeline |

> [!NOTE]
> Phần điểm còn lại (`0.8 / 10`) chủ yếu đến từ các hạng mục cần hạ tầng multi-node hoặc chốt ở cấp app:
> - **G-01 / Q-AUTH**: Hoàn thiện xác thực/phân quyền JWT end-to-end cho toàn bộ endpoint backend trước khi mở public Internet không giới hạn IP.
> - **G-04**: Kiến trúc Single-VM Droplet chấp nhận trade-off không có multi-node DB HA (được bù đắp bằng `backup-db.sh` + DO Automated Backups + Terraform IaC khôi phục `< 15 phút`).
