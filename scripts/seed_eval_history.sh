#!/bin/bash
# Rebuild the Evals run history with REAL runs after a DB reset: boots the
# backend against each artifact generation and runs the same eval through the
# product API, so the history page shows the v2 -> v3 story with true numbers.
set -eo pipefail
cd "$(dirname "$0")/../backend"
PORT="${SARVAM_PORT:-8001}"
API="http://127.0.0.1:$PORT"
H='-H Content-Type:application/json -H X-Demo-Role:admin -H X-Tenant-ID:t-acme'

run_one() {  # run_one <model_path> <model_id> <mode> <sft>
  lsof -ti tcp:"$PORT" | xargs -r kill 2>/dev/null || true; sleep 1
  SARVAM_MODEL_PATH="$1" SARVAM_MODEL_ID="$2" SARVAM_RUNTIME=llama_cpp \
    SARVAM_SEED_HISTORY=0 SARVAM_SFT_PROMPT="$4" \
    nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
    > /tmp/sel-backend.log 2>&1 &
  until curl -sf "$API/health" >/dev/null 2>&1; do sleep 1; done
  R=$(curl -s $H -X POST "$API/evals/run" -d "{\"mode\":\"$3\"}")
  echo "$R" | .venv/bin/python -c "import sys,json;r=json.load(sys.stdin);print('  ', '$2', '$3', 'verdict='+str(r.get('verdict')), 'acc='+str(r['metrics']['task_accuracy']))"
}

echo "eval history: fixture (rules engine)"
run_one "" "" fixture 0
echo "eval history: v2 artifact (broken training)"
run_one "$HOME/sarvam-soup/sarvam-1-triage-iq3xxs.gguf" "m-sarvam-mini-iq3xxs" local 0
echo "eval history: v3 artifact (fixed training)"
run_one "$HOME/sarvam-soup/sarvam-1-triage-v3e2-iq3xxs.gguf" "m-sarvam-mini-v3-iq3xxs" local 1
lsof -ti tcp:"$PORT" | xargs -r kill 2>/dev/null || true
echo "HISTORY_DONE (restart the demo backend with local_model.sh --keep-db)"
