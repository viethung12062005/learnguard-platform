# ADR-0002 — Frontend hosting: Azure Static Web Apps

- **Trạng thái:** Accepted
- **Ngày:** 2026-11-04

## Bối cảnh
FE là React/Vite SPA (client-side routing), build ra `dist/`, cần navigation fallback về `index.html`. Không có backend server-side.

## Quyết định
Host trên **Azure Static Web Apps** (Free/Standard), cung cấp `staticwebapp.config.json` (navigation fallback + response overrides). Env build-time `VITE_BACKEND_API_URL` trỏ tới API public.

## Hệ quả
- Public endpoint, không cần Network/RBAC.
- API được browser gọi trực tiếp (CORS), không qua SWA proxy → API phải public + CORS + (thiếu) auth (xem ADR-0006/threat model).
- Deploy qua `azure/static-web-apps-deploy` hoặc SWA CLI + deployment token (secret trong Key Vault).

## Cần xác minh
- Free tier có đủ cho nhu cầu (custom domain/SSL nếu cần) — dự kiến Standard cho prod nếu cần auth/custom domain.
