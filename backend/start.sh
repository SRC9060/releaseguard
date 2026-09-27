#!/bin/sh
set -e

echo "[ReleaseGuard] Running database migrations..."
alembic upgrade head

echo "[ReleaseGuard] Starting ingestion worker..."
python -m app.worker &
WORKER_PID=$!

cleanup() {
    echo "[ReleaseGuard] Shutting down worker..."
    kill "$WORKER_PID" 2>/dev/null || true
    wait "$WORKER_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

echo "[ReleaseGuard] Starting FastAPI..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}"
