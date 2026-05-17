#!/usr/bin/env bash
# MoneyPrinter Largo — launches both backend (FastAPI) and frontend (Vite)
# Run from the project root: bash webapp/start.sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -d "venv/bin" ]; then
  PY="$ROOT/venv/bin/python"
else
  PY="python"
fi

echo "[api] Starting FastAPI on http://127.0.0.1:8000 ..."
"$PY" -m uvicorn webapp.api.main:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

trap "kill $API_PID 2>/dev/null || true" EXIT

cd "$ROOT/webapp/web"
echo "[web] Starting Vite on http://127.0.0.1:5173 ..."
pnpm run dev
