#!/usr/bin/env python3
"""
Guardrail: chặn các resource mà role FSO-SandboxOps KHÔNG được phép tạo.

Dùng:
    terraform show -json tfplan > plan.json
    python scripts/guardrails/check_plan.py plan.json

Hoặc pipe:
    terraform show -json tfplan | python scripts/guardrails/check_plan.py

Exit code 1 nếu phát hiện resource bị cấm → dừng pipeline.
"""
from __future__ import annotations

import json
import sys

# Windows console thường là cp1252 → in tiếng Việt có dấu gây UnicodeEncodeError.
# Ép stdout/stderr về UTF-8 để script chạy được cả trên self-hosted runner Windows.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Không được phép: Microsoft.Authorization/*/Write + Delete (notActions của role).
FORBIDDEN_TYPES = {
    "azurerm_role_assignment",
    "azurerm_role_definition",
    "azurerm_policy_assignment",
    "azurerm_policy_definition",
    "azurerm_policy_set_definition",
    "azurerm_management_lock",
    "azurerm_resource_group_policy_assignment",
    "azurerm_subscription_policy_assignment",
}

WRITE_ACTIONS = {"create", "update", "delete"}


def _decode(raw: bytes) -> str:
    """Chịu được BOM: PowerShell `>` ghi UTF-8 BOM hoặc UTF-16LE."""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def load_plan() -> dict:
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as fh:
            return json.loads(_decode(fh.read()))
    return json.loads(_decode(sys.stdin.buffer.read()))


def main() -> int:
    plan = load_plan()
    changes = plan.get("resource_changes") or []

    violations: list[str] = []
    for rc in changes:
        actions = set(rc.get("change", {}).get("actions") or [])
        if not actions & WRITE_ACTIONS:
            continue  # read/no-op không tính
        rtype = rc.get("type", "")
        if rtype in FORBIDDEN_TYPES or rtype.startswith(
            ("azurerm_role_", "azurerm_policy_", "azurerm_management_lock")
        ):
            violations.append(f"{rtype} (address: {rc.get('address')}, actions: {sorted(actions)})")

    if violations:
        print("GUARDRAIL FAILED — plan chứa resource không được phép:\n", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nLý do: role FSO-SandboxOps có notActions chặn "
            "Microsoft.Authorization/*/Write+Delete.\n"
            "Các resource trên phải do Admin làm (xem runbooks/admin-requests.md).",
            file=sys.stderr,
        )
        return 1

    print(f"GUARDRAIL OK — {len(changes)} resource change, không có resource bị cấm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
