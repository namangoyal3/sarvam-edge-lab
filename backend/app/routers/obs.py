import json

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..common import ctx, network_online, content_logging, is_policy_stale, policy_stale_minutes, audit, require
from ..db import db, row, rows, tx, jload
from ..seed import utcnow

router = APIRouter(tags=["observability"])


@router.get("/telemetry")
def list_telemetry(limit: int = 100, execution_path: str | None = None,
                   success: int | None = None, synced: int | None = None):
    sql = "SELECT * FROM telemetry_events WHERE 1=1"
    params: list = []
    if execution_path:
        sql += " AND execution_path=?"
        params.append(execution_path)
    if success is not None:
        sql += " AND success=?"
        params.append(success)
    if synced is not None:
        sql += " AND synced=?"
        params.append(synced)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(min(limit, 500))
    out = rows(sql, tuple(params))
    for e in out:
        e["content_preview"] = e["content_preview"] if content_logging() else None
    return {
        "content_logging": content_logging(),
        "warning": ("Content logging is ON — demo mode only. Never enable in production."
                    if content_logging() else "Raw user content logging disabled (privacy default)."),
        "events": out}


@router.post("/telemetry/sync")
def telemetry_sync(fail_once: bool = False, ctxinfo: dict = Depends(ctx)):
    """Idempotent sync of locally-queued telemetry. Retries use exponential backoff."""
    pending = rows("SELECT * FROM offline_queue WHERE state IN ('pending','failed') "
                   "AND payload_type='telemetry_sync' ORDER BY id LIMIT 200")
    synced, skipped_dupes, failed = 0, 0, 0
    transient_fail = fail_once and len(pending) > 0
    with tx():
        from ..db import db
        for q in pending:
            p = jload(q["payload"])
            eid = p.get("event_id", "")
            already = db().execute("SELECT 1 FROM telemetry_events WHERE event_id=? AND synced=1", (eid,)).fetchone()
            if already:
                skipped_dupes += 1
                db().execute("UPDATE offline_queue SET state='synced' WHERE id=?", (q["id"],))
                continue
            if transient_fail:
                # simulate flaky network: backoff before retry
                att = q["attempts"] + 1
                from datetime import datetime, timedelta, timezone
                nxt = (datetime.now(timezone.utc) +
                       timedelta(seconds=min(2 ** att * 2, 60))).isoformat(timespec="seconds")
                db().execute("UPDATE offline_queue SET attempts=?, last_error='E_TRANSIENT_SIM', "
                           "next_attempt_at=?, state='failed' WHERE id=?", (att, nxt, q["id"]))
                failed += 1
                continue
            db().execute("UPDATE telemetry_events SET synced=1, queue_state='synced' WHERE event_id=?", (eid,))
            db().execute("UPDATE offline_queue SET state='synced', attempts=attempts+1, last_error=NULL WHERE id=?",
                       (q["id"],))
            synced += 1
    remaining = row("SELECT COUNT(*) c FROM offline_queue WHERE state IN ('pending','failed')")["c"]
    audit("telemetry.sync", ctxinfo=ctxinfo,
          result_summary=f"synced={synced} duplicates_skipped={skipped_dupes} retried_later={failed}")
    return {"synced": synced, "duplicates_skipped": skipped_dupes,
            "retrying_with_backoff": failed, "remaining_pending": remaining,
            "idempotent": True}


@router.get("/telemetry/queue")
def queue_view():
    items = rows("SELECT * FROM offline_queue ORDER BY id DESC LIMIT 100")
    return {"network_online": network_online(), "items": items,
            "pending_count": sum(1 for i in items if i["state"] in ("pending", "failed"))}


@router.get("/audit")
def audit_log(limit: int = 150, action: str | None = None):
    sql = "SELECT * FROM audit_events"
    params: list = []
    if action:
        sql += " WHERE action LIKE ?"
        params.append(f"%{action}%")
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(min(limit, 500))
    return {"disclaimer": "Demo audit log for interview purposes — NOT a certified compliance system.",
            "events": rows(sql, tuple(params))}


@router.get("/analytics/summary")
def analytics_summary(ctxinfo: dict = Depends(ctx)):
    tid = ctxinfo["tenant_id"]
    gen_share = row("SELECT AVG(is_generated) g, COUNT(*) n FROM telemetry_events WHERE tenant_id=?", (tid,))
    telem_all = rows("SELECT * FROM telemetry_events WHERE tenant_id=?", (tid,))
    succ_lat = sorted(e["latency_ms"] for e in telem_all if e["success"] and e["latency_ms"])
    local_n = sum(1 for e in telem_all if e["execution_path"] == "local")
    cloud_n = sum(1 for e in telem_all if e["execution_path"] == "cloud_simulator")
    queued = [e for e in telem_all if e["execution_path"] == "queued_offline"]
    errors = [e for e in telem_all if not e["success"]]
    devices = rows("SELECT * FROM devices WHERE tenant_id=?", (tid,))
    active = [d for d in devices if d["status"] != "disabled"]

    def pct(v, p):
        s = sorted(v)
        return s[min(len(s) - 1, int(len(s) * p / 100))] if s else 0

    # ---- product metrics
    users = rows("SELECT * FROM users WHERE tenant_id=?", (tid,))
    atfs = []
    for u in users:
        if u["first_success_at"] and u["activated_at"]:
            from datetime import datetime
            d = (datetime.fromisoformat(u["first_success_at"]) -
                 datetime.fromisoformat(u["activated_at"])).total_seconds() / 60
            atfs.append(d)
    reviews_open = row("SELECT COUNT(*) c FROM review_tasks WHERE status='open'")["c"]
    reviews_total = row("SELECT COUNT(*) c FROM review_tasks")["c"]
    reviews_resolved = row("SELECT COUNT(*) c FROM review_tasks WHERE status IN ('resolved','rejected') AND resolved_at IS NOT NULL")["c"]
    turnaround = []
    for r_ in rows("SELECT created_at, resolved_at FROM review_tasks WHERE resolved_at IS NOT NULL"):
        from datetime import datetime
        turnaround.append((datetime.fromisoformat(r_["resolved_at"]) -
                           datetime.fromisoformat(r_["created_at"])).total_seconds() / 60)
    rollouts = rows("SELECT * FROM update_rollouts")
    updates = [r for r in rollouts if r["kind"] == "update"]
    rollbacks = [r for r in rollouts if r["kind"] == "rollback"]
    compat_ok = sum(1 for d in devices if (d.get("compatibility_detail") or {}).get("status") == "compatible")

    # ---- time series (last 7 days buckets by day-hour blocks)
    series = _series(telem_all)

    # ---- unit economics
    cc = {c["key"]: c["value"] for c in rows("SELECT * FROM cost_config")}
    monthly_vol = cc.get("monthly_request_volume", 50000)
    cloud_share = cloud_n / max(local_n + cloud_n + len(queued), 1)
    human_rate = reviews_total / max(sum(1 for e in telem_all), 1)
    hardware_monthly = cc.get("hardware_cost_per_device_inr", 18000) / max(cc.get("amortize_months", 24), 1)
    monthly_cost = (hardware_monthly * max(len(active), 1)
                    + cc.get("local_ops_cost_device_month_inr", 40) * max(len(active), 1)
                    + cc.get("cloud_cost_per_request_inr", 0.85) * monthly_vol * cloud_share
                    + cc.get("human_support_cost_per_ticket_inr", 45) * monthly_vol * human_rate
                    + cc.get("model_update_cost_per_device_inr", 0.20) * max(len(active), 1) * 2)
    successful_monthly = int(monthly_vol * 0.94)

    return {
        "data_provenance": ("MIXED: recent events are live demo activity; historical baseline is generated "
                            "sample data" if gen_share["g"] and gen_share["g"] > 0.5 else "live demo data"),
        "offline_view": not network_online(),
        "policy_stale": is_policy_stale(),
        "cards": {
            "active_devices": len(active),
            "successful_workflows": sum(1 for e in telem_all if e["success"]),
            "local_execution_pct": round(100 * local_n / max(len(telem_all), 1), 1),
            "cloud_fallback_pct": round(100 * cloud_n / max(len(telem_all), 1), 1),
            "offline_queued_events": len(queued),
            "p50_latency_ms": pct(succ_lat, 50),
            "p95_latency_ms": pct(succ_lat, 95),
            "validation_failure_rate_pct": round(100 * sum(1 for e in errors if e["error_code"] == "E_SCHEMA_INVALID") / max(len(telem_all), 1), 2),
            "crash_error_count": len(errors),
            "current_model_version": (row("SELECT model_version v FROM devices WHERE model_version IS NOT NULL ORDER BY id LIMIT 1") or {}).get("v"),
            "pending_updates": row("SELECT COUNT(*) c FROM devices WHERE update_status!='up_to_date'", ())["c"],
        },
        "product_metrics": {
            "activation_to_first_success_min": round(sorted(atfs)[len(atfs) // 2], 1) if atfs else None,
            "workflows_per_active_device_day": round(
                sum(1 for e in telem_all if e["success"]) / 7 / max(len(active), 1), 1),
            "local_execution_pct": round(100 * local_n / max(len(telem_all), 1), 1),
            "cloud_fallback_pct": round(100 * cloud_n / max(len(telem_all), 1), 1),
            "offline_success_pct": round(100 * sum(1 for e in queued if e["success"]) / max(len(queued), 1), 1),
            "p50_ms": pct(succ_lat, 50), "p95_ms": pct(succ_lat, 95),
            "schema_validation_pct": round(100 - 100 * sum(1 for e in errors if e["error_code"] == "E_SCHEMA_INVALID") / max(len(telem_all), 1), 2),
            "critical_field_accuracy_note": "run an eval to compute live; latest eval gate shown below",
            "latest_eval_verdict": (row("SELECT verdict v FROM eval_runs ORDER BY started_at DESC LIMIT 1") or {}).get("v"),
            "repeat_usage_pct": round(_repeat_usage(tid), 1),
            "crash_error_rate_pct": round(100 * len(errors) / max(len(telem_all), 1), 2),
            "update_success_pct": round(100 * sum(1 for u in updates if u["state"] == 'success') / max(len(updates), 1), 1),
            "rollback_rate_pct": round(100 * len(rollbacks) / max(len(updates) + len(rollbacks), 1), 1),
            "hitl_escalation_pct": round(100 * reviews_total / max(row("SELECT COUNT(*) c FROM inference_requests WHERE tenant_id=?", (tid,))["c"], 1), 1),
            "review_turnaround_min": round(sorted(turnaround)[len(turnaround) // 2], 1) if turnaround else None,
            "device_compatibility_pct": round(100 * compat_ok / max(len(devices), 1), 1),
        },
        "unit_economics": {
            "assumptions": cc,
            "cost_per_successful_workflow_inr": round(monthly_cost / max(successful_monthly, 1), 3),
            "monthly_total_estimated_inr": round(monthly_cost, 0),
            "formula": "(hardware_amortised + ops + cloud*share + human*ticket_rate + updates) / successful_workflows",
        },
        "series": series,
        "fallback_reasons": _tally([e["fallback_reason"] or "none" for e in telem_all]),
        "error_taxonomy": _tally([e["error_code"] or "ok" for e in telem_all]),
        "routing_split": {"local": local_n, "cloud_simulator": cloud_n, "queued_offline": len(queued)},
        "policy_decisions": _tally([e["execution_path"] for e in telem_all]),
        "device_health": [{"id": d["id"], "status": d["status"], "battery": d["battery_pct"],
                           "thermal": d["thermal"], "compat": d["compatibility"]} for d in devices],
        "model_runtime_distribution": {
            "models": _tally([e["model_version"] or "?" for e in telem_all]),
            "runtimes": _tally([e["runtime_version"] or "?" for e in telem_all])},
        "reviews": {"open": reviews_open, "total": reviews_total},
    }


def _repeat_usage(tid: str) -> float:
    devs = rows("SELECT device_id, COUNT(*) c FROM inference_requests WHERE tenant_id=? AND status='completed' GROUP BY device_id", (tid,))
    multi = sum(1 for d in devs if d["c"] >= 2)
    return 100 * multi / max(len(devs), 1)


def _tally(items):
    out = {}
    for i in items:
        k = str(i)[:60]
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:8])


def _series(events):
    days = {}
    for e in events:
        day = (e["ts"] or "")[:10]
        b = days.setdefault(day, {"day": day, "local": 0, "cloud_simulator": 0, "queued_offline": 0,
                                  "errors": 0, "lat_sum": 0, "lat_n": 0})
        if e["execution_path"] in ("local", "cloud_simulator", "queued_offline"):
            b[e["execution_path"]] += 1
        if not e["success"]:
            b["errors"] += 1
        if e["success"] and e["latency_ms"]:
            b["lat_sum"] += e["latency_ms"]
            b["lat_n"] += 1
    out = sorted(days.values(), key=lambda x: x["day"])
    for o in out:
        o["avg_latency"] = int(o["lat_sum"] / o["lat_n"]) if o["lat_n"] else 0
        del o["lat_sum"], o["lat_n"]
    return out[-14:]


@router.get("/analytics/cost-config")
def get_cost_config():
    return rows("SELECT * FROM cost_config")


@router.post("/analytics/cost-config")
def set_cost_config(body: dict, ctxinfo: dict = Depends(ctx)):
    require(ctxinfo, "admin")
    allowed = {"hardware_cost_per_device_inr", "amortize_months", "local_ops_cost_device_month_inr",
               "cloud_cost_per_request_inr", "human_support_cost_per_ticket_inr",
               "model_update_cost_per_device_inr", "monthly_request_volume"}
    with tx():
        from ..db import db
        for k, v in body.items():
            if k in allowed:
                db().execute("UPDATE cost_config SET value=? WHERE key=?", (float(v), k))
    audit("analytics.cost_config_update", ctxinfo=ctxinfo, result_summary=str(body)[:120])
    return get_cost_config()
