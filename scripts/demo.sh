#!/usr/bin/env bash
# Sarvam Edge Lab — five-minute interview demo (API walkthrough).
# Requires: backend on $API (default http://localhost:8001). Frontend on :5173 for visuals.
set -e
API="${API:-http://localhost:8001}"
H='-H Content-Type:application/json'
step() { echo; echo "═══ STEP $1: $2 ═══"; }
jqpy() { .venv/bin/python -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

cd "$(dirname "$0")/.." || cd ..
PY="backend/.venv/bin/python"
[ -x "$PY" ] || PY=python3

step 1 "Run a local inference (simulation mode)"
R=$(curl -s $H -X POST "$API/inference" -d '{"text":"My payment of ₹4999 was charged twice, refund urgently","device_id":"DEV-1002","policy_id":"p-balanced"}')
echo "$R" | $PY -c "import sys,json;r=json.load(sys.stdin);print('status:',r['status'],'| path:',r['execution_path']);print('result:',{k:r['result'][k] for k in ('category','urgency','language','confidence')});print('label:',r['banner'])"

step 2 "Show model / runtime / device / latency metadata"
echo "$R" | $PY -c "import sys,json;r=json.load(sys.stdin);print('model:',r['model']);print('artifact:',r['artifact_path']);print('latency_ms:',r['latency_ms'],'| validation:',r['validation']['status'],'| audit:',r['audit_event_id'])"

step 3 "Switch device DEV-1009 to local-only policy"
curl -s $H -X POST "$API/devices/DEV-1009/policy?policy_id=p-local-only" | $PY -c "import sys,json;print('policy now:',json.load(sys.stdin)['policy_id'])"

step 4 "Disconnect the simulated network"
curl -s $H -X POST "$API/system/network" -d '{"online":false}'; echo

step 5 "Run another request successfully while offline (local keeps working)"
curl -s $H -X POST "$API/inference" -d '{"text":"App atak jata hai bahut slow hai","device_id":"DEV-1009"}' \
 | $PY -c "import sys,json;r=json.load(sys.stdin);print('status:',r['status'],'| path:',r['execution_path'],'(offline, on-device)')"

step 6 "Show offline telemetry queue + queue a cloud-path request"
curl -s $H -X POST "$API/inference" -d '{"text":"wifi not connecting","device_id":"DEV-1002","policy_id":"p-balanced","force_path":"cloud"}' \
 | $PY -c "import sys,json;r=json.load(sys.stdin);print('cloud request while offline ->',r['status'])"
curl -s "$API/telemetry/queue" | $PY -c "import sys,json;q=json.load(sys.stdin);items=q['items'];print('queue size:',len(items),'| pending:',sum(1 for i in items if i['state'] in ('pending','failed')))"

step 7 "Trigger a low-confidence result (forced [low] marker)"
LR=$(curl -s $H -X POST "$API/inference" -d '{"text":"[low] my name is Rohit billing issue urgent","device_id":"DEV-1002"}')
echo "$LR" | $PY -c "import sys,json;r=json.load(sys.stdin);print('status:',r['status'],'| confidence:',r['result']['confidence'],'-> HITL review created')"

step 8 "Approve it through HITL"
REV=$(curl -s "$API/reviews?status=open" | $PY -c "import sys,json;rs=json.load(sys.stdin);print([r['id'] for r in rs if r['correlation_id']=='$(echo "$LR" | $PY -c "import sys,json;print(json.load(sys.stdin)['correlation_id'])")'][0])")
curl -s $H -X POST "$API/reviews/$REV/action" -d '{"action":"approve","reason":"verified with customer by phone"}' \
 | $PY -c "import sys,json;print('review',sys.stdin.read()[:60],'...')"

step 9 "Reconnect the device (network restored, queued jobs execute)"
curl -s $H -X POST "$API/devices/DEV-1002/reconnect" \
 | $PY -c "import sys,json;r=json.load(sys.stdin);print('telemetry synced:',r['telemetry_synced'],'| queued jobs executed:',r['queued_jobs_executed'])"

step 10 "Sync remaining telemetry idempotently"
curl -s $H -X POST "$API/telemetry/sync" ; echo

step 11 "Change the model version on DEV-1004 (update rollout)"
curl -s $H -X POST "$API/devices/DEV-1004/update?target_model_id=m-triage-rules-sim&target_version=1.5.0" \
 | $PY -c "import sys,json;print('device model_version ->',json.load(sys.stdin)['model_version'])"

step 12 "Roll it back"
curl -s $H -X POST "$API/devices/DEV-1004/rollback" \
 | $PY -c "import sys,json;d=json.load(sys.stdin);print('rolled back to ->',d['model_version'],'| update_status:',d['update_status'])"

step 13 "Open the audit log"
curl -s "$API/audit?limit=5" | $PY -c "import sys,json;[print('-',e['ts'][11:19],e['action'],e.get('approval_status') or '') for e in json.load(sys.stdin)['events']]"

step 14 "Run evals and compare simulation vs cloud simulator"
A=$(curl -s $H -X POST "$API/evals/run" -d '{"mode":"fixture"}' | $PY -c "import sys,json;print(json.load(sys.stdin)['eval_run_id'])")
B=$(curl -s $H -X POST "$API/evals/run" -d '{"mode":"cloud_sim"}' | $PY -c "import sys,json;print(json.load(sys.stdin)['eval_run_id'])")
for R in $A $B; do curl -s "$API/evals/$R" | $PY -c "import sys,json;d=json.load(sys.stdin);m=d['metrics'];print(d['mode'].ljust(10),'accuracy:',m['task_accuracy'],'schema_valid:',m['schema_validity_rate'],'p95:',m['p95_latency_ms'],'ms | verdict gates:', {k:v['pass'] for k,v in d['gates'].items()})"; done

echo
echo "✅ Demo script complete. Open http://localhost:5173 for the visual tour."
