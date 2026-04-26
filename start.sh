#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

# Backend
echo "Starting backend (PARQUET mode) on :8000..."
source .venv/bin/activate
SEAHEALTH_API_MODE=parquet uvicorn seahealth.api.main:app --reload --port 8000 &
BACKEND_PID=$!

# Wait for backend to bind
until curl -sf http://localhost:8000/health >/dev/null 2>&1; do sleep 0.3; done
echo "Backend ready — $(curl -s http://localhost:8000/health/data | python -c 'import json,sys; d=json.load(sys.stdin); print(f"mode={d[\"mode\"]} retriever={d[\"retriever_mode\"]}")')"

# Frontend
echo "Starting frontend (live mode) on :5173..."
cd app
VITE_SEAHEALTH_API_MODE=live VITE_SEAHEALTH_API_BASE=http://localhost:8000 npm run dev &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT INT TERM

echo ""
echo "  Backend:  http://localhost:8000/health/data"
echo "  Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both."
wait
