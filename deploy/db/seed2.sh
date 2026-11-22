#!/bin/bash
# LearnGuard — seed2: reset least-privilege role passwords + seed Key Vault.
# Idempotent. Dùng lại /tmp/lg.env. Không in secret.
set -euo pipefail
source /tmp/lg.env
log(){ echo "[seed2] $*"; }

export PGPASSWORD="$PG_ADMIN_PW"
PSQL="psql -h $PG_FQDN -p 5432 -U $PG_ADMIN_LOGIN -d $PG_DB -v ON_ERROR_STOP=1 -At"

log "public tables: $($PSQL -c "select count(*) from pg_tables where schemaname='public'")"

API_PW=$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 32)
ML_PW=$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 32)
$PSQL -c "ALTER ROLE lg_api WITH LOGIN PASSWORD '${API_PW}';" >/dev/null
$PSQL -c "ALTER ROLE lg_ml_writer WITH LOGIN PASSWORD '${ML_PW}';" >/dev/null

API_DSN="postgresql://lg_api:${API_PW}@${PG_FQDN}:5432/${PG_DB}?sslmode=require"
ML_DSN="postgresql://lg_ml_writer:${ML_PW}@${PG_FQDN}:5432/${PG_DB}?sslmode=require"

log "api login: $(PGPASSWORD="$API_PW" psql -h "$PG_FQDN" -U lg_api -d "$PG_DB" -Atc "select 'ok'" 2>&1)"
log "ml  login: $(PGPASSWORD="$ML_PW" psql -h "$PG_FQDN" -U lg_ml_writer -d "$PG_DB" -Atc "select 'ok'" 2>&1)"

log "az login --identity --allow-no-subscriptions"
az login --identity --allow-no-subscriptions --only-show-errors >/dev/null 2>&1 || { echo "AZ LOGIN FAILED"; az login --identity --allow-no-subscriptions 2>&1 | tail -5; exit 1; }

log "seed KV $KV_NAME"
# Không bật xtrace: --value chứa secret.
az keyvault secret set --vault-name "$KV_NAME" --name pg-admin-password   --value "$PG_ADMIN_PW" --only-show-errors >/dev/null
az keyvault secret set --vault-name "$KV_NAME" --name pg-dsn              --value "$API_DSN"    --only-show-errors >/dev/null
az keyvault secret set --vault-name "$KV_NAME" --name pg-dsn-ml           --value "$ML_DSN"     --only-show-errors >/dev/null
az keyvault secret set --vault-name "$KV_NAME" --name acr-admin-password  --value "$ACR_PW"     --only-show-errors >/dev/null

log "secrets now:"
az keyvault secret list --vault-name "$KV_NAME" --query "[].name" -o tsv 2>&1
rm -f /tmp/lg.env
log "DONE"
