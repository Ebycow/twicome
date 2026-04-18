# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# 辞書をビルド時にロードして初期化チェック
RUN python -c "import sudachipy; d = sudachipy.Dictionary(dict='full'); t = d.create(); print('sudachi ok:', t.tokenize('テスト')[0].surface())"

COPY main.py .

EXPOSE 8200

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8200"]
