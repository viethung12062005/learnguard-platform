#!/bin/bash
# LearnGuard — seed trong VNet: DB schema + role least-privilege + secret Key Vault.
# Chạy TRÊN jump VM. Đọc giá trị từ /tmp/lg.env (chmod 600) và XOÁ file đó khi xong.
# KHÔNG in giá trị secret ra stdout.
#
# Idempotent: chạy lại nhiều lần vẫn đúng. Mật khẩu role được sinh mới mỗi lần chạy
# rồi ghi đè vào Key Vault, nên không cần biết mật khẩu cũ.
#
# Dùng khi: triển khai mới, redeploy, hoặc nghi ngờ secret trong KV bị lệch.
set -euo pipefail

source /tmp/lg.env

log() { echo "[seed] $*"; }

export PGPASSWORD="$PG_ADMIN_PW"
PSQL="psql -h $PG_FQDN -p 5432 -U $PG_ADMIN_LOGIN -d $PG_DB -v ON_ERROR_STOP=1 -At"

# ---------------------------------------------------------------------------
# 1. Schema
# ---------------------------------------------------------------------------
log "1/5 Apply schema (db_schema_seed.sql)"
psql -h "$PG_FQDN" -p 5432 -U "$PG_ADMIN_LOGIN" -d "$PG_DB" -v ON_ERROR_STOP=1 \
  -f /tmp/db_schema_seed.sql >/tmp/schema.log 2>&1 \
  || { echo "SCHEMA FAILED"; tail -20 /tmp/schema.log; exit 1; }

# ---------------------------------------------------------------------------
# 2. Role least-privilege
#    PostgreSQL không có CREATE ROLE IF NOT EXISTS → tạo có điều kiện, rồi ALTER
#    để đặt mật khẩu (bước này chạy được cả khi role đã tồn tại).
# ---------------------------------------------------------------------------
log "2/5 Create/refresh least-privilege roles (lg_api, lg_ml_writer)"
API_PW=$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 32)
ML_PW=$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 32)

$PSQL -c "DO \$do\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lg_api') THEN
    CREATE ROLE lg_api LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lg_ml_writer') THEN
    CREATE ROLE lg_ml_writer LOGIN;
  END IF;
END
\$do\$;" >/dev/null

$PSQL -c "ALTER ROLE lg_api       WITH LOGIN PASSWORD '${API_PW}';" >/dev/null
$PSQL -c "ALTER ROLE lg_ml_writer WITH LOGIN PASSWORD '${ML_PW}';"  >/dev/null

# roles.sql chứa CREATE ROLE (có placeholder mật khẩu) → bỏ các dòng đó vì role
# đã được tạo/đặt mật khẩu ở trên; giữ lại toàn bộ GRANT / ALTER TABLE OWNER.
sed -e "s|<PASSWORD_API>|$API_PW|g" -e "s|<PASSWORD_ML_WRITER>|$ML_PW|g" \
  /tmp/roles.sql | grep -v '^CREATE ROLE' > /tmp/roles.rendered.sql
$PSQL -f /tmp/roles.rendered.sql >/tmp/roles.log 2>&1 \
  || { echo "ROLES FAILED"; tail -20 /tmp/roles.log; exit 1; }
rm -f /tmp/roles.rendered.sql

# ---------------------------------------------------------------------------
# 3. DSN
# ---------------------------------------------------------------------------
log "3/5 Build DSNs"
API_DSN="postgresql://lg_api:${API_PW}@${PG_FQDN}:5432/${PG_DB}?sslmode=require"
ML_DSN="postgresql://lg_ml_writer:${ML_PW}@${PG_FQDN}:5432/${PG_DB}?sslmode=require"

# ---------------------------------------------------------------------------
# 4. Đăng nhập Key Vault bằng managed identity của VM
#    --allow-no-subscriptions: identity không có RBAC subscription (đúng guardrail);
#    quyền data-plane đến từ access policy gắn cho identity của VM.
# ---------------------------------------------------------------------------
log "4/5 az login --identity --allow-no-subscriptions"
az login --identity --allow-no-subscriptions --only-show-errors >/dev/null 2>&1 \
  || { echo "AZ LOGIN FAILED"; az login --identity --allow-no-subscriptions 2>&1 | tail -5; exit 1; }

# ---------------------------------------------------------------------------
# 5. Seed secret
#    Không bật xtrace: --value chứa secret.
# ---------------------------------------------------------------------------
log "5/5 Seed Key Vault secrets into $KV_NAME"
az keyvault secret set --vault-name "$KV_NAME" --name pg-admin-password    --value "$PG_ADMIN_PW" --only-show-errors >/dev/null
az keyvault secret set --vault-name "$KV_NAME" --name pg-dsn               --value "$API_DSN"    --only-show-errors >/dev/null
az keyvault secret set --vault-name "$KV_NAME" --name pg-dsn-ml            --value "$ML_DSN"     --only-show-errors >/dev/null
az keyvault secret set --vault-name "$KV_NAME" --name acr-admin-password   --value "$ACR_PW"     --only-show-errors >/dev/null

# Kiểm tra đăng nhập DB bằng chính role vừa tạo (không in mật khẩu).
log "api login: $(PGPASSWORD="$API_PW" psql -h "$PG_FQDN" -U lg_api       -d "$PG_DB" -Atc "select 'ok'" 2>&1)"
log "ml  login: $(PGPASSWORD="$ML_PW"  psql -h "$PG_FQDN" -U lg_ml_writer -d "$PG_DB" -Atc "select 'ok'" 2>&1)"

log "Secrets:"
az keyvault secret list --vault-name "$KV_NAME" --query "[].name" -o tsv 2>/dev/null
log "Tables:"
$PSQL -c "select tablename from pg_tables where schemaname='public' order by 1" 2>/dev/null
log "Roles:"
$PSQL -c "select rolname from pg_roles where rolname like 'lg_%' order by 1" 2>/dev/null

# Dọn file chứa secret.
rm -f /tmp/lg.env /tmp/roles.rendered.sql
log "DONE"
