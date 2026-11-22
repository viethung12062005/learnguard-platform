# LearnGuard — Threat Model (STRIDE, tóm tắt)

> File "kiến thức" → không commit. Phạm vi: 5 luồng chính. Bám FR-08, FR-09, Privacy.
> Ký hiệu cột "Việc cần làm": ✅ = đã có trong code/schema, 🟡 = phải làm ở hạ tầng, 🔴 = gap cần quyết/chờ backend.

## Luồng 1 — Advisor → SWA → API

| STRIDE | Mối đe doạ | Control đã có | Rủi ro chấp nhận / Việc cần làm |
|---|---|---|---|
| Spoofing | Không auth → ai cũng giả advisor | Không (M6 chưa có) | 🔴 **Q-AUTH**: chờ backend M6 hay chấp nhận mock? |
| Tampering | Sửa request giữa browser↔API | TLS (HTTPS) | ✅ |
| Repudiation | Truy cập prediction không lưu vết | `audit_logs` (schema sẵn, chưa implement) | 🟡 backend M7 ghi audit mỗi lần truy cập |
| Info Disclosure | Lộ dự đoán do API public + no auth | CORS hạn chế origin | 🔴 auth + không `CORS_ORIGINS=*` |
| DoS | API public bị flood | CAE scale rule + IP restriction | 🟡 thêm rate limit |
| EoP | — (chưa có role) | — | 🟡 phân quyền advisor/admin khi M6 |

## Luồng 2 — API → PostgreSQL

| STRIDE | Mối đe doạ | Control đã có | Rủi ro chấp nhận / Việc cần làm |
|---|---|---|---|
| Spoofing/Tampering | SQL injection | SQLAlchemy parameterized | ✅ |
| Info Disclosure | API user đọc quá quyền | Tách user `lg_api` chỉ SELECT | ✅ (làm ở tầng PG) |
| EoP | Leak DSN → full DB | TLS + secret trong KV + user tách quyền | ✅ |
| DoS | Cạn pool DB | Giới hạn pool size | 🟡 cấu hình pool |

## Luồng 3 — ML job → PostgreSQL / Azure Files

| STRIDE | Mối đe doạ | Control đã có | Rủi ro chấp nhận / Việc cần làm |
|---|---|---|---|
| Tampering | Data/artifact bị sửa | SHA-256 ingestion + manifest + M3 gates | ✅ |
| Info Disclosure | DSN/key lộ trong env/log | Secret trong KV, không log | ✅ |
| EoP | `lg_ml_writer` drop bảng | GRANT chỉ INSERT/UPDATE/SELECT trên `ml_predictions` | ✅ (làm ở tầng PG) |
| Repudiation | Không biết run nào ghi gì | `run_id`/`model_version`/`scored_at` | ✅ |

## Luồng 4 — CI/CD → Azure

| STRIDE | Mối đe doạ | Control đã có | Rủi ro chấp nhận / Việc cần làm |
|---|---|---|---|
| Spoofing | Giả token deploy | OIDC (GitHub ký) + pin identity | ✅ |
| Tampering | Image bị tráo | Pin image theo digest + build từ source app ở git ref cố định | ✅ |
| EoP | CI UAMI có Contributor (rộng) | Custom role ít quyền nếu được; prod approval gate | 🟡 **Q-RBAC**: Admin gán role, cân nhắc custom role tối thiểu |
| Info Disclosure | Secret trong log | `::add-mask::`, KV | ✅ |

## Luồng 5 — API → LLM (OpenRouter)

| STRIDE | Mối đe doạ | Control đã có | Rủi ro chấp nhận / Việc cần làm |
|---|---|---|---|
| Info Disclosure | Gửi PII lên LLM | Backend chỉ gửi context tối thiểu (pseudonymous `student_key`) | 🟡 enforce + test |
| Tampering | Prompt injection / output sai schema | Validate output LLM theo schema | 🟡 test |
| DoS/Chi phí | Lạm dụng làm tăng chi phí | `LLM_MAX_*_TOKENS`, timeout, retry, fallback | ✅ |
| Repudiation | Không truy được lần gọi | Bảng `llm_calls` (không log prompt/response) | ✅ |

## Ghi nhận rủi ro chấp nhận (dự án học tập)

1. **API không auth** cho tới khi backend M6 xong → đây là gap bảo mật lớn nhất. Chấp nhận CHỈ khi người dùng xác nhận (Q-AUTH); nếu không → chặn deploy prod tới khi có auth.
2. ~~**PG firewall theo dải egress IP**~~ → **đã giải quyết**: PG chuyển sang **private endpoint** (public_network_access=Disabled), API/Job VNet-integrated. Không còn phụ thuộc egress IP (Q-FW đóng).
3. **1 role-assignment** (CI UAMI → RG) là bất khả kháng, do Admin gán → không thể loại bỏ (Q-RBAC).
