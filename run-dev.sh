#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_ACTIVATE="$ROOT_DIR/.venv/bin/activate"

if [[ ! -f "$VENV_ACTIVATE" ]]; then
  echo "Missing virtual environment at $VENV_ACTIVATE"
  echo "Create it first: python3.11 -m venv .venv && source .venv/bin/activate && cd backend && pip install -e '.[dev]'"
  exit 1
fi

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "Missing frontend/package.json at $FRONTEND_DIR"
  exit 1
fi

backend_pid=""
frontend_pid=""

cleanup() {
  local exit_code=$?
  trap - INT TERM EXIT

  if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill "$backend_pid" 2>/dev/null || true
  fi
  if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" 2>/dev/null; then
    kill "$frontend_pid" 2>/dev/null || true
  fi

  wait 2>/dev/null || true
  exit "$exit_code"
}

trap cleanup INT TERM EXIT

echo "Starting backend on http://127.0.0.1:8000"
(
  cd "$ROOT_DIR"
  source "$VENV_ACTIVATE"
  exec uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
) &
backend_pid=$!

sleep 1
if ! kill -0 "$backend_pid" 2>/dev/null; then
  echo "Backend failed to start"
  exit 1
fi

echo "Starting frontend on http://127.0.0.1:3000"
(
  cd "$FRONTEND_DIR"
  exec npm run dev
) &
frontend_pid=$!

sleep 1
if ! kill -0 "$frontend_pid" 2>/dev/null; then
  echo "Frontend failed to start"
  exit 1
fi

echo "Both services are running. Press Ctrl+C to stop both."

while true; do
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    echo "Backend process exited"
    exit 1
  fi
  if ! kill -0 "$frontend_pid" 2>/dev/null; then
    echo "Frontend process exited"
    exit 1
  fi
  sleep 1
done
