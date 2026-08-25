"""Inference orchestration: policy gate -> runtime -> validation -> HITL -> records."""
import json

from . import seed, settings
from .common import (ctx as req_ctx, network_online, content_logging, telemetry, audit,
                     enqueue, is_policy_stale)
from .db import db, row, rows, tx, jdump
from .engine import triage as T
from .engine.policy import evaluate, Decision, needs_hitl
from .engine.runtimes import run_fixture, run_local, run_cloud_sim
from .schemas import InferInput, validate_triage

DEFAULT_MODEL = "m-triage-rules-sim"


def _cost(key: str, default: float) -> float:
    r = row("SELECT value FROM cost_config WHERE key=?", (key,))
    return r["value"] if r else default


def _local_available(model_id: str, device: dict | None) -> tuple[bool, str]:
    """The embedded rules engine always runs on-device. A user-provided artifact
    counts as available only when its file + runtime exist AND the device can run it."""
    if model_id == DEFAULT_MODEL:
        return True, "embedded rules engine"
    st = settings.active_mode()
    if st["mode"] != "real_local":
        return False, st.get("reason", "user-provided Sarvam-1 artifact unavailable")
    if device:
        from .engine import compat as C
        model = row("SELECT * FROM models WHERE id=?", (model_id,))
        verdict = C.check(device, model)
        if verdict["status"] == "incompatible":
            return False, "device cannot run this model: " + "; ".join(verdict["reasons"])
    return True, f"real local model loaded ({st.get('runtime')})"


def _select_model(inp: InferInput, device: dict | None) -> str:
    if inp.force_path == "cloud":
        return "m-cloud-large-ref"
    if inp.model_id:
        return inp.model_id
    if device and device.get("model_id"):
        return device["model_id"]
    return DEFAULT_MODEL


def run_pipeline(inp: InferInput, ctxinfo: dict, *, request_id: str | None = None,
                 correlation_id: str | None = None, from_queue: bool = False) -> dict:
    now = seed.utcnow()
    rid = request_id or seed.rid("req")
    corr = correlation_id or seed.rid("corr")
    tenant = ctxinfo["tenant_id"]
    device = row("SELECT * FROM devices WHERE id=?", (inp.device_id,)) if inp.device_id else None
    if inp.device_id and not device:
        raise ValueError(f"unknown device {inp.device_id}")
    if not inp.device_id and device is None:
        device = row("SELECT * FROM devices WHERE tenant_id=? AND status='online' ORDER BY id LIMIT 1", (tenant,))
        inp.device_id = device["id"] if device else None

    policy = row("SELECT * FROM policies WHERE id=?", (inp.policy_id or (device["policy_id"] if device else None) or "p-balanced",))
    model_id = _select_model(inp, device)
    model = row("SELECT * FROM models WHERE id=?", (model_id,))
    input_bytes = len(inp.text.encode())
    online = network_online()
    stale = is_policy_stale()
    trace: list[dict] = []

    def step(name: str, detail: str):
        trace.append({"step": name, "detail": detail, "ts": seed.utcnow()})

    step("input_received", f"{input_bytes} bytes; language_hint={inp.language_hint}; "
         f"content_logged={'yes' if content_logging() else 'no (privacy default)'}")
    lang_guess = T.detect_language(inp.text)
    step("preprocessing", f"detected language≈{lang_guess}; truncated-safe; charset normalised")

    # ---------------- policy gate (before any inference)
    local_ok, local_why = _local_available(model_id, device)
    decision: Decision = evaluate(
        {"mode": policy["mode"], "offline_queue_enabled": policy["offline_queue_enabled"],
         "max_input_bytes": policy["max_input_bytes"], "allowed_data_classes": policy["allowed_data_classes"],
         "allowed_models": policy["allowed_models"], "allowed_device_ids": policy["allowed_device_ids"]},
        inp.text,
        {"network_online": online, "local_available": local_ok, "model_id": model_id,
         "device_id": inp.device_id, "force_path": inp.force_path})

    step("model_selected", f"{model_id} v{model['version'] if model else '?'} ({model['kind'] if model else '?'})")
    rt_name = ("cloud-simulator" if decision.outcome == "run_cloud"
               else (settings.active_mode().get("runtime", "llama_cpp") if model_id != DEFAULT_MODEL
                     else "python-embedded"))
    step("runtime_selected", f"{rt_name}")
    hw = (f"{device['chipset']} / NPU={device['gpu_npu']}" if device else "server-host (demo)")
    step("hardware_backend_selected",
         hw + (" — CPU threadpool" if decision.outcome == "run_local" else " — simulated cloud node"))

    def persist(status, exec_path, result=None, validation="valid", latency=0, cost=0.0,
                fb_reason=None, mver=None, rver=None):
        mver = mver or (model["version"] if model else "?")
        rver = rver or rt_name
        with tx() as c:
            c.execute("""INSERT INTO inference_requests(id,correlation_id,tenant_id,device_id,user_id,
                        policy_id,model_id,input_bytes,language_hint,status,execution_path,fallback_reason,
                        latency_ms,estimated_cost_inr,validation_status,requested_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET status=excluded.status, execution_path=excluded.execution_path,
                          fallback_reason=excluded.fallback_reason, latency_ms=excluded.latency_ms,
                          estimated_cost_inr=excluded.estimated_cost_inr, validation_status=excluded.validation_status""",
                      (rid, corr, tenant, inp.device_id, ctxinfo["user_id"], policy["id"], model_id,
                       input_bytes, inp.language_hint, status, exec_path, fb_reason, latency, cost,
                       validation, now))
            result_id = None
            if result:
                ver = c.execute("SELECT COALESCE(MAX(version),0)+1 v FROM inference_results WHERE request_id=?",
                                (rid,)).fetchone()["v"]
                result_id = seed.rid("res")
                c.execute("""INSERT INTO inference_results(id,request_id,version,category,urgency,language,
                            suggested_next_action,confidence,explanation,model_version,runtime_version,created_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (result_id, rid, ver, result["category"], result["urgency"], result["language"],
                           result["suggested_next_action"], result["confidence"], result["explanation"],
                           mver, rver, now))
        return result_id

    if decision.outcome == "rejected":
        step("inference_started", "skipped — policy rejected before execution")
        step("validation", "not reached")
        step("policy_decision", f"REJECTED: {'; '.join(decision.reasons)}")
        step("output_returned", "policy-blocked result returned; no data left the device")
        eid = persist("rejected", "policy_blocked", None, "skipped_by_policy")
        telem = telemetry(tenant_id=tenant, device_id=inp.device_id, correlation_id=corr,
                          model_version=model_id, runtime_version=rt_name,
                          policy_version=policy["version"], execution_path="policy_blocked",
                          success=False, error_code="E_POLICY_REJECTED", input_bytes=input_bytes,
                          output_bytes=0, text=inp.text)
        aud = audit("inference.rejected", ctxinfo=ctxinfo, device_id=inp.device_id,
                    policy_version=policy["version"], model_version=model_id, correlation_id=corr,
                    reason="; ".join(decision.reasons), result_summary="no result produced")
        return _response(rid, corr, "rejected", "policy_blocked", None, validation={"status": "skipped_by_policy", "errors": []},
                         latency=0, cost=0.0, fb="; ".join(decision.reasons), policy=policy,
                         decision=decision, trace=trace, audit_id=aud, telemetry_id=eid, mver=model_id)

    step("inference_started", f"path={decision.outcome}")

    if decision.outcome == "queue_offline":
        why = "; ".join(decision.reasons)
        step("validation", "deferred until reconnect")
        step("policy_decision", f"QUEUED OFFLINE: {why}")
        step("output_returned", "request parked in bounded local queue; will execute on reconnect")
        q = enqueue("inference_job", {"infer_input": inp.model_dump(mode="json"),
                                      "request_id": rid, "correlation_id": corr}, key=rid)
        eid = persist("queued_offline", "queued_offline", None, "deferred", 0, 0.0, fb_reason=why)
        telemetry(tenant_id=tenant, device_id=inp.device_id, correlation_id=corr,
                  model_version=model_id, runtime_version=rt_name, policy_version=policy["version"],
                  execution_path="queued_offline", success=True, fallback_reason=why,
                  input_bytes=input_bytes, output_bytes=0, queue_state="pending_sync", text=inp.text)
        aud = audit("inference.queued_offline", ctxinfo=ctxinfo, device_id=inp.device_id,
                    policy_version=policy["version"], model_version=model_id, correlation_id=corr,
                    reason=why, result_summary=f"queue_key={q['key']}")
        return _response(rid, corr, "queued_offline", "queued_offline", None,
                         validation={"status": "deferred", "errors": []}, latency=0, cost=0.0,
                         fb=why, policy=policy, decision=decision, trace=trace, audit_id=aud,
                         telemetry_id=q["key"], mver=model_id,
                         banner="Request queued locally — network offline / cloud prohibited by policy")

    # ---------------- actual inference
    seed_text = corr
    if decision.outcome == "run_cloud":
        res = run_cloud_sim(inp.text, inp.language_hint if inp.language_hint != "auto" else None,
                            seed_text, _cost("cloud_cost_per_request_inr", 0.85))
    elif model_id == DEFAULT_MODEL:
        res = run_fixture(inp.text, inp.language_hint if inp.language_hint != "auto" else None, seed_text)
    else:
        res = run_local(inp.text, inp.language_hint if inp.language_hint != "auto" else None, seed_text)

    parsed, errs = validate_triage(res.result)
    val_status = "valid" if (parsed and res.validation_status == "valid") else "invalid"
    step("validation", f"typed schema TriageResult: {val_status}" + (f" errors={errs[:2]}" if errs else ""))

    hitl, hitl_why = needs_hitl(parsed.confidence if parsed else 0.0,
                                parsed.category if parsed else "other",
                                val_status == "valid", policy, stale_offline=(stale and not from_queue))

    step("policy_decision", f"{decision.outcome.upper()}: {'; '.join(decision.reasons)}"
         + (f"; HITL escalation={hitl_why}" if hitl else ""))
    step("output_returned", f"status={'needs_review' if hitl else 'completed'}; "
         f"label='{res.label}'" + (f"; fallback={res.fallback_reason}" if res.fallback_reason else ""))

    status = "needs_review" if hitl else "completed"
    result_id = persist(status, "cloud_simulator" if decision.outcome == "run_cloud" else "local",
                        res.result, val_status, res.latency_ms, res.cost_inr, res.fallback_reason,
                        res.model_version, res.runtime_version)
    path_label = "cloud_simulator" if decision.outcome == "run_cloud" else "local"
    telem = telemetry(tenant_id=tenant, device_id=inp.device_id, correlation_id=corr,
                      model_version=res.model_version, runtime_version=res.runtime_version,
                      policy_version=policy["version"],
                      execution_path=path_label,
                      event_id=f"evt_{corr[:18]}_{path_label}",   # T5: idempotent on drain retries
                      latency_ms=res.latency_ms, success=val_status == "valid",
                      error_code=None if val_status == "valid" else "E_SCHEMA_INVALID",
                      fallback_reason=res.fallback_reason, confidence=res.result.get("confidence"),
                      input_bytes=input_bytes,
                      output_bytes=len(json.dumps(res.result).encode()), text=inp.text)
    aud = audit("inference.completed" if not hitl else "inference.needs_review",
                ctxinfo=ctxinfo, device_id=inp.device_id, policy_version=policy["version"],
                model_version=res.model_version, approval_status=("pending" if hitl else "auto"),
                correlation_id=corr, reason=hitl_why or None,
                result_summary=f"{res.result['category']}/{res.result['urgency']} conf={res.result['confidence']}")
    if hitl and not row("SELECT 1 FROM review_tasks WHERE correlation_id=?", (corr,)):   # T5 dedupe
        with tx():
            db().execute("""INSERT INTO review_tasks(id,request_id,correlation_id,tenant_id,reason_code,
                          detail,original_result,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                         (seed.rid("rev"), rid, corr, tenant, hitl_why,
                          f"confidence={res.result.get('confidence')} category={res.result.get('category')} "
                          f"stale_policy={stale}", jdump(res.result), "open", seed.utcnow()))

    return _response(rid, corr, status, "cloud_simulator" if decision.outcome == "run_cloud" else "local",
                     res.result, validation={"status": val_status, "errors": errs},
                     latency=res.latency_ms, cost=res.cost_inr, fb=res.fallback_reason,
                     policy=policy, decision=decision, trace=trace, audit_id=aud,
                     telemetry_id=telem, mver=res.model_version, rver=res.runtime_version,
                     label=res.label, model_id=model_id)


def _response(rid, corr, status, path, result, *, validation, latency, cost, fb, policy,
              decision, trace, audit_id, telemetry_id, mver, rver=None, label=None,
              banner=None, model_id=None):
    simulated = label is not None and "Real local" not in label
    return {
        "request_id": rid, "correlation_id": corr, "status": status, "execution_path": path,
        "label": label or "", "banner": banner or (label if simulated else ""),
        "simulated": simulated,
        "result": result,
        "validation": validation,
        "latency_ms": latency, "estimated_cost_inr": round(cost, 4),
        "fallback_reason": fb,
        "model": {"id": model_id or mver, "version": mver,
                  "runtime_version": rver},
        "artifact_path": settings.MODEL_PATH or "(none — simulation mode)",
        "policy": {"id": policy["id"], "name": policy["name"], "version": policy["version"],
                   "mode": policy["mode"], "last_synced_at": policy["last_synced_at"],
                   **decision.to_dict()},
        "network_online": network_online(),
        "trace": trace,
        "audit_event_id": audit_id, "telemetry_event_id": telemetry_id,
        "disclaimer": "Demo build — outputs are NOT Sarvam Edge production benchmarks.",
    }


# ------------------------------------------------------------------ queue drain

def drain_inference_queue() -> int:
    items = rows("SELECT * FROM offline_queue WHERE payload_type='inference_job' AND state IN ('pending','failed')")
    n = 0
    for it in items:
        payload = json.loads(it["payload"])
        try:
            inp = InferInput(**payload["infer_input"])
            dev = row("SELECT tenant_id FROM devices WHERE id=?", (inp.device_id,)) if inp.device_id else None
            ctxinfo = {"role": "admin", "tenant_id": dev["tenant_id"] if dev else "t-acme",
                       "user_id": "u-naman"}
            run_pipeline(inp, ctxinfo,
                         request_id=payload["request_id"], correlation_id=payload["correlation_id"],
                         from_queue=True)
            with tx():
                db().execute("UPDATE offline_queue SET state='done', attempts=attempts+1, last_error=NULL WHERE id=?",
                             (it["id"],))
            n += 1
        except Exception as e:   # backoff: next attempt in 2^attempts * 2 s
            att = it["attempts"] + 1
            from datetime import datetime, timedelta, timezone
            nxt = (datetime.now(timezone.utc) + timedelta(seconds=min(2 ** att * 2, 60))).isoformat(timespec="seconds")
            with tx():
                db().execute("UPDATE offline_queue SET state='failed', attempts=?, last_error=?, next_attempt_at=? WHERE id=?",
                             (att, str(e)[:200], nxt, it["id"]))
    return n
