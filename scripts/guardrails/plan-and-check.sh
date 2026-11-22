#!/usr/bin/env bash
# Chạy terraform plan rồi kiểm tra guardrail trước khi apply.
# Dùng: bash scripts/guardrails/plan-and-check.sh <env-dir> [out-plan]
set -euo pipefail

ENV_DIR="${1:-infra/env/dev}"
PLAN_FILE="${2:-tfplan}"

pushd "$ENV_DIR" >/dev/null

echo "==> terraform init"
terraform init -input=false

echo "==> terraform validate"
terraform validate

echo "==> terraform plan -> $PLAN_FILE"
terraform plan -input=false -out="$PLAN_FILE"

echo "==> guardrail"
terraform show -json "$PLAN_FILE" | python "$(git rev-parse --show-toplevel)/scripts/guardrails/check_plan.py"

echo
echo "Plan an toàn theo guardrail. Chạy apply bằng:"
echo "  cd $ENV_DIR && terraform apply $PLAN_FILE"

popd >/dev/null
