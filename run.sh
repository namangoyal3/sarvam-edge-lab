#!/usr/bin/env bash
# Sarvam Edge Lab — one-command local run.
#   ./run.sh            start backend (:8001) + frontend (:5173)
#   ./run.sh --reset    wipe the demo database first
set -e
cd "$(dirname "$0")"

if [ "$1" = "--reset" ]; then
  rm -rf backend/data
  echo "database reset"
fi

# ---- backend ----
cd backend
[ -d .venv ] || uv venv --python 3.11 .venv || python3.11 -m venv .venv
.venv/bin/python -m pip install -q -r requirements.txt
mkdir -p data
nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${SARVAM_PORT:-8001}" \
  > /tmp/sel-backend.log 2>&1 &
BACK_PID=$!
echo "backend  → http://localhost:${SARVAM_PORT:-8001}  (logs: /tmp/sel-backend.log)"

# ---- frontend ----
cd ../frontend
[ -d node_modules ] || npm install
VITE_API_PROXY="http://localhost:${SARVAM_PORT:-8001}" nohup npx vite --port 5173 \
  > /tmp/sel-frontend.log 2>&1 &
FRONT_PID=$!
echo "frontend → http://localhost:5173              (logs: /tmp/sel-frontend.log)"

trap "kill $BACK_PID $FRONT_PID 2>/dev/null" EXIT
echo
echo "Sarvam Edge Lab running. Ctrl-C to stop."
wait
