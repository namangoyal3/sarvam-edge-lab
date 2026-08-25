#!/bin/bash
U=http://localhost:8001; H="-H Content-Type:application/json"; A='-H X-Demo-Role:admin'
pass=0; fail=0
chk(){ if [ "$1" = "$2" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $3 (got $1 want $2)"; fi }
# 1 health + mode
chk "$(curl -s $U/health | python3 -c 'import sys,json;print(json.load(sys.stdin)["mode"])')" "real_local" "health real_local"
# 2 sim inference (default rules model)
chk "$(curl -s $H -X POST $U/inference -d '{"text":"wifi not working","device_id":"DEV-1001"}' | python3 -c 'import sys,json;r=json.load(sys.stdin);print(r["status"] in ("completed","needs_review") and r["simulated"])')" "True" "sim inference"
# 3 real-model inference
R=$(curl -s $H -X POST $U/inference -d '{"text":"₹5000 charged twice refund","device_id":"DEV-1002","model_id":"m-sarvam-mini-iq2m"}')
chk "$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["label"])')" "Real local model" "real-model label"
chk "$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["validation"]["status"])')" "valid" "real-model schema"
# 4 cloud simulator
chk "$(curl -s $H -X POST $U/inference -d '{"text":"app slow","force_path":"cloud"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["execution_path"])')" "cloud_simulator" "cloud sim"
# 5 offline cycle: disconnect -> force cloud queues -> reconnect drains
curl -s $H -X POST $U/system/network -d '{"online":false}' > /dev/null
Q=$(curl -s $H -X POST $U/inference -d '{"text":"net down test","force_path":"cloud","policy_id":"p-balanced"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])')
chk "$Q" "queued_offline" "offline queueing"
REC=$(curl -s --max-time 180 $H -X POST $U/devices/DEV-1002/reconnect | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["queued_jobs_executed"]>=1 and d["status"]=="online")')
chk "$REC" "True" "reconnect drains"
# 6 HITL flow
LR=$(curl -s $H -X POST $U/inference -d '{"text":"[low] odd ticket","device_id":"DEV-1002"}')
TID=$(echo "$LR" | python3 -c "import sys,json;r=json.load(sys.stdin);print(next(t['id'] for t in __import__('urllib.request',fromlist=['x']).urlopen('$U/reviews?status=open') if False) if False else '')")
TID=$(curl -s "$U/reviews?status=open" | python3 -c "import sys,json;rs=json.load(sys.stdin);print(rs[0]['id'] if rs else '')")
if [ -n "$TID" ]; then chk "$(curl -s $H -X POST $U/reviews/$TID/action -d '{"action":"approve","reason":"verified"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])')" "resolved" "HITL approve"; else echo "FAIL: no open review"; fail=$((fail+1)); fi
# 7 update/rollback
chk "$(curl -s $H -X POST "$U/devices/DEV-1004/update?target_version=9.9.9-test" | python3 -c 'import sys,json;print(json.load(sys.stdin)["model_version"])')" "9.9.9-test" "update rollout"
chk "$(curl -s $H -X POST $U/devices/DEV-1004/rollback | python3 -c 'import sys,json;print(json.load(sys.stdin)["update_status"])')" "rolled_back" "rollback"
# 8 RBAC
chk "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -H 'X-Demo-Role: viewer' $U/devices/DEV-1001/offline -d '{}')" "403" "RBAC viewer block"
# 9 audit + telemetry + analytics
chk "$(curl -s "$U/audit?limit=3" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["events"])>0)')" "True" "audit populated"
chk "$(curl -s $U/analytics/summary -H 'X-Demo-Role: admin' -o /dev/null -w '%{http_code}')" "200" "analytics"
chk "$(curl -s "$U/telemetry?limit=5" -o /dev/null -w '%{http_code}')" "200" "telemetry"
# 10 evals endpoint
chk "$(curl -s $H -X POST $U/evals/run -d '{"mode":"fixture"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["metrics"]["task_accuracy"])')" "1.0" "eval fixture acc"
# 11 diagnostics never-connected
chk "$(curl -s $U/devices/DEV-1012/diagnostics | python3 -c 'import sys,json;print("NEVER" in json.load(sys.stdin)["note_central_analytics"].upper())')" "True" "never-connected diagnostics"
echo "=============================="
echo "PASS=$pass FAIL=$fail"
