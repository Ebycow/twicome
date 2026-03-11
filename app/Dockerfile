# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY main.py .
COPY app_factory.py .
COPY faiss_search.py .
COPY cache.py .
COPY core/ ./core/
COPY services/ ./services/
COPY repositories/ ./repositories/
COPY routers/ ./routers/
COPY templates/ ./templates/
COPY static/ ./static/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
