#!/usr/bin/env bash
# =============================================================================
# LearnGuard — Idempotent PostgreSQL Initialization & Least-Privilege Roles
#
# Executed automatically by postgres:16-alpine inside `/docker-entrypoint-initdb.d/`
# on initial volume creation, OR invoked manually via `docker compose exec postgres`
# during deployments to guarantee ml_predictions schema and role permissions stay
# synchronized without colliding with `db-migrate` (`alembic upgrade head`).
#
# Ownership boundaries:
#   - `lg_ml_writer`: owns `public.ml_predictions` (CRUD). No access to backend tables/sequences.
#   - `lg_api`      : SELECT on `public.ml_predictions`; CRUD on backend tables & sequences
#                     (including future tables created by `alembic upgrade head` via DEFAULT PRIVILEGES).
# =============================================================================
set -euo pipefail

log() {
  echo "[init-db] $(date -u +"%Y-%m-%dT%H:%M:%SZ") - $*"
}

DB_USER="${POSTGRES_USER:-lgadmin}"
DB_NAME="${POSTGRES_DB:-learnguard}"
API_PW="${LG_API_PASSWORD:-}"
ML_PW="${LG_ML_WRITER_PASSWORD:-}"

if [[ -z "${API_PW}" || -z "${ML_PW}" ]]; then
  log "ERROR: LG_API_PASSWORD and LG_ML_WRITER_PASSWORD must be set in environment."
  exit 1
fi

PSQL=("psql" "-v" "ON_ERROR_STOP=1" "--username" "${DB_USER}" "--dbname" "${DB_NAME}")

log "1/3 Ensuring public.ml_predictions table and columns exist..."
"${PSQL[@]}" <<'EOSQL'
CREATE TABLE IF NOT EXISTS public.ml_predictions (
    student_key character(16) NOT NULL,
    code_module character varying NOT NULL,
    code_presentation character varying NOT NULL,
    split character varying NOT NULL,
    risk_score double precision,
    predicted_label smallint,
    threshold double precision,
    uncertainty double precision,
    status character varying NOT NULL,
    review_reason character varying,
    model_version character varying NOT NULL,
    snapshot_version character varying NOT NULL,
    cutoff_day integer NOT NULL,
    top_signals_json text,
    features_json text,
    run_id character varying NOT NULL,
    scored_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ml_predictions_pkey PRIMARY KEY (code_module, code_presentation, student_key)
);

ALTER TABLE public.ml_predictions
    ADD COLUMN IF NOT EXISTS features_json text;

CREATE INDEX IF NOT EXISTS ml_predictions_model_version_idx
    ON public.ml_predictions USING btree (model_version);
CREATE INDEX IF NOT EXISTS ml_predictions_status_idx
    ON public.ml_predictions USING btree (status);
EOSQL

log "2/3 Creating/updating least-privilege roles (lg_api, lg_ml_writer)..."
"${PSQL[@]}" \
  --set=api_pw="${API_PW}" \
  --set=ml_pw="${ML_PW}" <<'EOSQL'
DO $do$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lg_api') THEN
    CREATE ROLE lg_api LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lg_ml_writer') THEN
    CREATE ROLE lg_ml_writer LOGIN;
  END IF;
END
$do$;

ALTER ROLE lg_api WITH LOGIN PASSWORD :'api_pw';
ALTER ROLE lg_ml_writer WITH LOGIN PASSWORD :'ml_pw';
EOSQL

log "3/3 Applying least-privilege grants and default privileges for Alembic migrations..."
"${PSQL[@]}" <<'EOSQL'
-- ML writer owns ml_predictions only
GRANT USAGE ON SCHEMA public TO lg_ml_writer;
GRANT CREATE ON SCHEMA public TO lg_ml_writer;
ALTER TABLE public.ml_predictions OWNER TO lg_ml_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ml_predictions TO lg_ml_writer;

-- API role reads ml_predictions and gets full CRUD on backend-owned tables
GRANT USAGE ON SCHEMA public TO lg_api;
GRANT SELECT ON public.ml_predictions TO lg_api;

-- Ensure future tables/sequences created by `db-migrate` (alembic upgrade head) grant CRUD to lg_api
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lg_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO lg_api;

-- Grant CRUD to lg_api on any backend tables that already exist
DO $grants$
DECLARE
  tbl text;
  backend_tables text[] := ARRAY[
    'users',
    'audit_logs',
    'briefs',
    'decisions',
    'llm_calls',
    'chat_sessions',
    'chat_messages',
    'alembic_version'
  ];
BEGIN
  FOREACH tbl IN ARRAY backend_tables LOOP
    IF to_regclass('public.' || tbl) IS NOT NULL THEN
      EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO lg_api', tbl);
    END IF;
  END LOOP;
END
$grants$;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO lg_api;
EOSQL

log "PostgreSQL initialization and least-privilege role setup completed successfully."
