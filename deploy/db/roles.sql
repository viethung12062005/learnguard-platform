-- =====================================================================
-- LearnGuard — least-privilege DB roles
--
-- Hai vùng sở hữu (xem db_schema_seed.sql header):
--   - ml-data   : ml_predictions  (M5 upsert; backend chỉ SELECT)
--   - backend   : users, audit_logs, briefs, decisions, llm_calls,
--                 chat_sessions, chat_messages
--
-- Roles:
--   - lg_ml_writer : pipeline M5 ghi (upsert) ml_predictions; KHÔNG đọc backend.
--   - lg_api       : backend API — CRUD các bảng backend + SELECT ml_predictions.
--
-- Nạp từ phía có quyền admin sau khi đã chạy `alembic upgrade head`:
--   psql -U lgadmin -d learnguard -f roles.sql
--   (thay <PASSWORD> bằng giá trị thật; mật khẩu KHÔNG commit)
-- =====================================================================

-- Roles không phải superuser, không tạo DB/role.
CREATE ROLE lg_ml_writer WITH LOGIN PASSWORD '<PASSWORD_ML_WRITER>';
CREATE ROLE lg_api       WITH LOGIN PASSWORD '<PASSWORD_API>';

-- ---------------------------------------------------------------------
-- lg_ml_writer — chỉ sở hữu miền ml_predictions
-- ---------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO lg_ml_writer;
-- cần CREATE để predictions_store.ensure_schema() chạy CREATE TABLE IF NOT EXISTS
-- (PostgreSQL kiểm tra quyền schema TRƯỚC khi thấy bảng đã tồn tại).
GRANT CREATE ON SCHEMA public TO lg_ml_writer;
-- CREATE INDEX IF NOT EXISTS yêu cầu quyền OWNER bảng → chuyển sở hữu miền ml-data.
ALTER TABLE public.ml_predictions OWNER TO lg_ml_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ml_predictions TO lg_ml_writer;

-- ---------------------------------------------------------------------
-- lg_api — backend: CRUD các bảng backend + SELECT ml_predictions
-- ---------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO lg_api;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.users         TO lg_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.audit_logs    TO lg_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.briefs        TO lg_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.decisions     TO lg_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.llm_calls     TO lg_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_sessions TO lg_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_messages TO lg_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.alembic_version TO lg_api; -- alembic upgrade

-- Backend chỉ ĐỌC prediction (không ghi, không xoá).
GRANT SELECT ON public.ml_predictions TO lg_api;

-- sequence cho các bảng backend (users/audit_logs/briefs/decisions/llm_calls/chat_*).
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO lg_api;

-- Mặc định cho bảng tạo mới trong tương lai (Alembic migration).
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lg_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO lg_api;
