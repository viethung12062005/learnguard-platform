# LearnGuard — Hardened Multi-Stage Production Dockerfile for Data & ML Batch Pipeline (Data-ML-MLOPS)
# Build context = Data-ML-MLOPS repository root.
# Build command:
#   docker build -f learnguard-platform/deploy/docker/Dockerfile.ml -t ghcr.io/<org>/learnguard-ml:<tag> ./Data-ML-MLOPS

# ---------------------------------------------------------------------------
# Stage 1: Build virtual environment with pinned ML dependencies
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade "pip>=25.0" "setuptools>=78.1.1" "wheel>=0.46.2" && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps .

# ---------------------------------------------------------------------------
# Stage 2: Minimal non-root runtime image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="learnguard-ml" \
      org.opencontainers.image.description="LearnGuard M1-M5 Batch Scoring, Drift Triage & Continual Retraining Worker" \
      org.opencontainers.image.source="https://github.com/ntk223/Data-ML-MLOPS"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    MPLCONFIGDIR=/tmp/learnguard-matplotlib \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

WORKDIR /app

# Apply latest Debian security patches (e.g. zlib1g), remove system setuptools/ensurepip outside /opt/venv, and create unprivileged user (UID/GID 10001)
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/* /usr/local/lib/python*/ensurepip /usr/local/lib/python*/site-packages/setuptools* /usr/lib/python*/dist-packages/setuptools* && \
    groupadd --gid 10001 learnguard && \
    useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin learnguard && \
    mkdir -p /tmp/learnguard-matplotlib /mnt/data/oulad /mnt/data/artifacts && \
    chown -R learnguard:learnguard /tmp/learnguard-matplotlib /mnt/data

COPY --from=builder /opt/venv /opt/venv
COPY src ./src
COPY db ./db

RUN chown -R learnguard:learnguard /app

USER learnguard:learnguard

ENTRYPOINT ["learnguard"]
CMD ["--help"]
