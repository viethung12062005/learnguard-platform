# P0.1 — Đối chiếu sự thật 3 repo app

> Nguồn: đọc code trực tiếp 3 repo app ngày 2026-11-04. File "kiến thức" → không commit.
> Snapshot SHA đã đọc (working tree clean, branch `main`):

| Repo | HEAD SHA | Remotes |
|---|---|---|
| `BE-MLOPS` | `899711e3e2926c95c1e383f16477c515861f3cab` | `origin/main` |
| `Data-ML-MLOPS` | `eed3e0c4c5bb578dbfe58c35e921f580fb2f69ef` | `origin/main` |
| `FE-MLOPS` | `4770a31ec0cd92c71b076e43a307e686ea648e4c` | `origin/main` |

Kết luận: `PROJECT_CONTEXT.md` (snapshot 2026-11-04) **khớp** với code. Các điểm cần bổ/sửa nhỏ ghi ở §4.

---

## 1. Backend `BE-MLOPS`

- Python >=3.10; FastAPI + uvicorn[standard]; SQLAlchemy 2; psycopg[binary]; pydantic-settings; LiteLLM; python-jose; passlib[bcrypt]; alembic (migrations/).
- **Alembic KHÔNG nằm trong `dependencies` của `pyproject.toml`** → image phải cài thêm `alembic` (app-change-request).
- Entrypoint `uvicorn learnguard_backend.main:app`; `main.py` khi chạy trực tiếp bind `127.0.0.1:8000` → container PHẢI chạy `--host 0.0.0.0 --port 8000`.
- Settings (`settings.py`): đọc env + `.env` ở root (`load_dotenv(..., override=False)`). `DATABASE_URL` ưu tiên, fallback `LEARNGUARD_PG_DSN`. LLM qua `LLM_API_BASE` (OpenRouter) + `LLM_API_KEY` + fallback Ollama.
  - Lưu ý: default `llm_model="gemini-3.8-flash"` trong code, nhưng `.env.example` dùng `openrouter/google/gemini-2.5-flash:free` → phải đặt `LLM_MODEL` rõ ràng qua env ở prod.
- **Auth CHƯA CÓ** (M6, `api/auth.py` raise `NotImplementedError`). Endpoint `/predictions` hiện không xác thực → rủi ro bảo mật (xem threat model + OPEN_QUESTIONS Q-AUTH).
- Không có Dockerfile.
- DB contract: `docs/DB_CONTRACT.md` v1.0 rev2 — backend sở hữu `users/briefs/decisions/llm_calls/audit_logs`; chỉ SELECT `ml_predictions`.

## 2. ML/Data `Data-ML-MLOPS`

- Python >=3.11; pandas 3.1.0, pyarrow 26.0.0, scikit-learn 1.7.2, joblib, scipy, psycopg[binary] 3.3.6, sqlalchemy 2.1.6 (pin trong `requirements.txt`).
- CLI `learnguard ml {preprocess, verify-preprocessor, train-logistic, verify-model, score}` (entry `learnguard.cli:main`).
- M1→M3 **không có CLI**, chạy bằng Python heredoc (xem `docs/DEPLOY_VPS.md` §5.1 `cron_pipeline.sh`).
- Score→DB: `score --pg-dsn $LEARNGUARD_PG_DSN --pg-table ml_predictions` (upsert all-or-nothing; exit 0/1/2).
- ML là **batch**, không mở port; job chạy M1→M5; M4 train chạy thủ công khi ra model mới.

### 2.1 Path tương đối hard-code ảnh hưởng mount Azure Files

| Vị trí | Path | Ghi chú |
|---|---|---|
| `src/learnguard/settings.py:26-27` | `data_dir=Path("data/oulad")`, `artifacts_dir=Path("artifacts")` | Default tương đối CWD; override được qua env `LEARNGUARD_DATA_DIR` / `LEARNGUARD_ARTIFACTS_DIR` |
| `src/learnguard/cli.py:21,31,43` | `--artifacts-dir` default `Path("artifacts")` | **Argparse KHÔNG đọc env** — env chỉ ảnh hưởng `Settings`, không ảnh hưởng default của CLI flag |
| `src/learnguard/cli.py:134` | score output `artifacts_dir/"prediction-batches"/run_id/"predictions.parquet"` | artifact M5 |
| `src/learnguard/ml/training.py:222` | `artifacts_dir/"model-runs"/run_id` | artifact M4 |
| `src/learnguard/ml/preprocessing.py:218` | `artifacts_dir/"preprocessing-runs"/run_id` | artifact M4 |
| `src/learnguard/data/ingestion.py` | đọc `data_dir/<table>.csv`, ghi `output_dir/{canonical,quarantine}` | M1 |
| `docs/DEPLOY_VPS.md`, `docs/PIPELINE_GUIDE.md` | toàn bộ dùng `data/oulad/archive`, `artifacts/...` với **cwd = ml-data/** | wrapper job phải tái tạo đúng cwd |

**Hệ quả thiết kế (cho build/wrapper):** job container phải đặt `WORKDIR` sao cho `artifacts/` và `data/oulad/` trỏ tới mount Azure Files, **hoặc** truyền `--artifacts-dir`/`--snapshot`/`--data-dir` tường minh. Vì CLI `--artifacts-dir` không đọc env, wrapper nên `cd` vào mount rồi chạy, hoặc ghi `LEARNGUARD_DATA_DIR`/`LEARNGUARD_ARTIFACTS_DIR` **và** truyền `--artifacts-dir` tường minh.

### 2.2 Ước lượng tài nguyên (chưa chạy local — số "ước lượng" trừ khi ghi "đo")

| Mục | Giá trị | Nguồn |
|---|---|---|
| Zip nguồn | ~43MB (commit trong repo `data/archive.zip`) | repo |
| Giải nén | ~464MB, 7 CSV (studentVle.csv ~454MB, ~10.6M dòng) | `PIPELINE_GUIDE.md` |
| Disk | >= 5GB (data + artifacts + venv) | `DEPLOY_VPS.md` §1 |
| RAM | >= 2GB (docs); **peak M2 chưa đo** — ước lượng 2–4GB vì pandas nạp studentVle ~454MB | ước lượng, cần chạy local để đo thật |
| Thời gian M1→M5 | chưa đo | chưa chạy local |
| Snapshot M2 | ~27,535 dòng × 21 cột | `PIPELINE_GUIDE.md` §5.1 |

## 3. Frontend `FE-MLOPS`

- React 18.3, react-router-dom 6, TypeScript 5.7, Vite 5.4.
- Build `npm ci && npm run build` (`tsc --noEmit && vite build`) → `dist/`.
- Env build-time: `VITE_BACKEND_API_URL`, `VITE_USE_MOCK` (bake vào bundle).
- SPA routing → cần navigation fallback về `index.html` (platform repo cung cấp `staticwebapp.config.json`).
- **Không có `vite.config.*`** (Vite dùng default; `@vitejs/plugin-react` có trong devDeps nhưng không được cấu hình). Build vẫn chạy nhờ esbuild transform mặc định — cần xác minh khi build thật.
- `login/briefs/stats` = mock (chờ backend M6/M8); `predictions` = real API.

## 4. Điểm lệch/thiếu so với PROJECT_CONTEXT.md

1. PROJECT_CONTEXT ghi LLM default "gemini-3.8-flash" → thực tế `.env.example` dùng `openrouter/google/gemini-2.5-flash:free`. Cần đặt `LLM_MODEL` rõ ở prod.
2. Bổ sung SHA đã đọc (bảng đầu file này).
3. Bổ sung: CLI `--artifacts-dir` không đọc env (quan trọng cho wrapper job).
