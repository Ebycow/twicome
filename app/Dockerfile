# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# ── テスト・lint 用（docker-compose.dev.yml の test / lint サービスが target: dev で使う）──
FROM base AS dev
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt

# ── 本番ランタイム（既定ターゲット）──────────────────────────────────────────
FROM base AS runtime

COPY main.py .
COPY app_factory.py .
COPY clients/ ./clients/
COPY core/ ./core/
COPY services/ ./services/
COPY repositories/ ./repositories/
COPY routers/ ./routers/
COPY templates/ ./templates/
COPY static/ ./static/

EXPOSE 8000

# 単一ワーカー。--no-access-log でログ量（ディスク）を抑える
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
