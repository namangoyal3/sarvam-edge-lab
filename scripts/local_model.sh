#!/usr/bin/env bash
# Run Sarvam Edge Lab against the real sub-1GB Sarvam-1 artifact and make every
# dashboard number come from that model.
#
#   bash scripts/local_model.sh              # reset + load model + drive real traffic + start UI
#   bash scripts/local_model.sh --keep-db    # same, but keep existing records
#
# Env overrides: SARVAM_MODEL_PATH, SARVAM_MODEL_ID, SARVAM_PORT
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
PORT="${SARVAM_PORT:-8001}"
API="http://127.0.0.1:$PORT"
PY=backend/.venv/bin/python

# Prefer the newest fixed fine-tune when it exists; fall back to the v2 artifact.
# v3e2 (epoch-2) measured best at 966MB: 0.56 vs 0.52 (e1) vs 0.36 (v2)
if [ -z "${SARVAM_MODEL_PATH:-}" ] && [ -f "$HOME/sarvam-soup/sarvam-1-triage-v3e2-iq3xxs.gguf" ]; then
  export SARVAM_MODEL_PATH="$HOME/sarvam-soup/sarvam-1-triage-v3e2-iq3xxs.gguf"
  export SARVAM_MODEL_ID="${SARVAM_MODEL_ID:-m-sarvam-mini-v3-iq3xxs}"
elif [ -z "${SARVAM_MODEL_PATH:-}" ] && [ -f "$HOME/sarvam-soup/sarvam-1-triage-v3-iq3xxs.gguf" ]; then
  export SARVAM_MODEL_PATH="$HOME/sarvam-soup/sarvam-1-triage-v3-iq3xxs.gguf"
  export SARVAM_MODEL_ID="${SARVAM_MODEL_ID:-m-sarvam-mini-v3-iq3xxs}"
fi
export SARVAM_MODEL_PATH="${SARVAM_MODEL_PATH:-$HOME/sarvam-soup/sarvam-1-triage-iq3xxs.gguf}"
export SARVAM_MODEL_ID="${SARVAM_MODEL_ID:-m-sarvam-mini-iq3xxs}"
export SARVAM_RUNTIME=llama_cpp
export SARVAM_SEED_HISTORY=0          # dashboards must show real traffic only
# v3 artifacts are trained on the short prompt; serve them the same way.
case "$(basename "$SARVAM_MODEL_PATH")" in *-v3*-*|*-v3-*) export SARVAM_SFT_PROMPT=1;; esac

[ -f "$SARVAM_MODEL_PATH" ] || { echo "artifact not found: $SARVAM_MODEL_PATH"; exit 1; }
echo "artifact : $SARVAM_MODEL_PATH ($(du -h "$SARVAM_MODEL_PATH" | cut -f1))"
echo "catalog  : $SARVAM_MODEL_ID"

# ---- stop anything already bound to the port
lsof -ti tcp:"$PORT" | xargs -r kill 2>/dev/null || true
sleep 1

# ---- fresh database unless told otherwise
if [ "${1:-}" != "--keep-db" ]; then
  rm -rf backend/data
  echo "database : reset (synthetic 7-day backfill disabled)"
fi
mkdir -p backend/data

# ---- backend
cd backend
[ -x .venv/bin/python ] || { echo "backend venv missing — run ./run.sh once first"; exit 1; }
nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
  > /tmp/sel-backend.log 2>&1 &
cd "$ROOT"

for _ in $(seq 1 60); do
  MODE=$(curl -sf "$API/health" | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["mode"])' 2>/dev/null || true)
  [ -n "${MODE:-}" ] && break
  sleep 1
done
[ "${MODE:-}" = "real_local" ] || { echo "backend did not reach real_local mode (got '${MODE:-none}'); see /tmp/sel-backend.log"; exit 1; }
echo "backend  : $API  mode=real_local"

# ---- point the fleet at the local artifact, then drive real inference through it
"$PY" scripts/drive_local.py --api "$API" --model "$SARVAM_MODEL_ID"

# ---- frontend
cd frontend
[ -d node_modules ] || npm install
lsof -ti tcp:5173 | xargs -r kill 2>/dev/null || true
VITE_API_PROXY="$API" nohup npx vite --port 5173 > /tmp/sel-frontend.log 2>&1 &
cd "$ROOT"
echo
echo "UI       : http://localhost:5173   (backend log /tmp/sel-backend.log)"
