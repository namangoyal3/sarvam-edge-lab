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
    # T8: aggregate in SQLite; pull only the columns Python genuinely needs
    total_n = row("SELECT COUNT(*) n FROM telemetry_events WHERE tenant_id=?", (tid,))["n"]
    succ_lat = [r["latency_ms"] for r in rows(
        "SELECT latency_ms FROM telemetry_events WHERE tenant_id=? AND success=1 AND latency_ms>0", (tid,))]
    path_counts = {r["k"]: r["n"] for r in rows(
        "SELECT execution_path k, COUNT(*) n FROM telemetry_events WHERE tenant_id=? GROUP BY execution_path", (tid,))}
    local_n = path_counts.get("local", 0)
    cloud_n = path_counts.get("cloud_simulator", 0)
    queued_n = path_counts.get("queued_offline", 0)
    errors = row("SELECT COUNT(*) n FROM telemetry_events WHERE tenant_id=? AND success=0", (tid,))["n"]
    schema_errs = row("SELECT COUNT(*) n FROM telemetry_events WHERE tenant_id=? AND error_code='E_SCHEMA_INVALID'", (tid,))["n"]
    queued_ok = row("SELECT COUNT(*) n FROM telemetry_events WHERE tenant_id=? AND execution_path='queued_offline' AND success=1", (tid,))["n"]
    devices = rows("SELECT * FROM devices WHERE tenant_id=?", (tid,))
    active = [d for d in devices if d["status"] != "disabled"]

    def tally_sql(col):
        return {r["k"]: r["n"] for r in rows(
            f"SELECT {col} k, COUNT(*) n FROM telemetry_events WHERE tenant_id=? GROUP BY {col} ORDER BY n DESC LIMIT 8", (tid,))
            if r["k"]}

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
    series = _series_sql(tid)

    # ---- unit economics
    cc = {c["key"]: c["value"] for c in rows("SELECT * FROM cost_config")}
    monthly_vol = cc.get("monthly_request_volume", 50000)
    cloud_share = cloud_n / max(local_n + cloud_n + queued_n, 1)
    human_rate = reviews_total / max(total_n, 1)
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
            "successful_workflows": row("SELECT COUNT(*) n FROM telemetry_events WHERE tenant_id=? AND success=1", (tid,))["n"],
            "local_execution_pct": round(100 * local_n / max(total_n, 1), 1),
            "cloud_fallback_pct": round(100 * cloud_n / max(total_n, 1), 1),
            "offline_queued_events": queued_n,
            "p50_latency_ms": pct(succ_lat, 50),
            "p95_latency_ms": pct(succ_lat, 95),
            "validation_failure_rate_pct": round(100 * schema_errs / max(total_n, 1), 2),
            "crash_error_count": errors,
            "current_model_version": (row("SELECT model_version v FROM devices WHERE model_version IS NOT NULL ORDER BY id LIMIT 1") or {}).get("v"),
            "pending_updates": row("SELECT COUNT(*) c FROM devices WHERE update_status!='up_to_date'", ())["c"],
        },
        "product_metrics": {
            "activation_to_first_success_min": round(sorted(atfs)[len(atfs) // 2], 1) if atfs else None,
            "workflows_per_active_device_day": round(
                row("SELECT COUNT(*) n FROM telemetry_events WHERE tenant_id=? AND success=1", (tid,))["n"] / 7 / max(len(active), 1), 1),
            "local_execution_pct": round(100 * local_n / max(total_n, 1), 1),
            "cloud_fallback_pct": round(100 * cloud_n / max(total_n, 1), 1),
            "offline_success_pct": 100.0 if queued_n == 0 else round(100 * queued_ok / max(queued_n, 1), 1),
            "p50_ms": pct(succ_lat, 50), "p95_ms": pct(succ_lat, 95),
            "schema_validation_pct": round(100 - 100 * schema_errs / max(total_n, 1), 2),
            "critical_field_accuracy_note": "run an eval to compute live; latest eval gate shown below",
            "latest_eval_verdict": (row("SELECT verdict v FROM eval_runs ORDER BY started_at DESC LIMIT 1") or {}).get("v"),
            "repeat_usage_pct": round(_repeat_usage(tid), 1),
            "crash_error_rate_pct": round(100 * errors / max(total_n, 1), 2),
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
        "fallback_reasons": {("none" if not k else k): v for k, v in tally_sql("fallback_reason").items()} or {"none": total_n},
        "error_taxonomy": tally_sql("error_code") or {"ok": total_n},
        "routing_split": {"local": local_n, "cloud_simulator": cloud_n, "queued_offline": queued_n},
        "policy_decisions": path_counts,
        "device_health": [{"id": d["id"], "status": d["status"], "battery": d["battery_pct"],
                           "thermal": d["thermal"], "compat": d["compatibility"]} for d in devices],
        "model_runtime_distribution": {
            "models": tally_sql("model_version") or {"?": total_n},
            "runtimes": tally_sql("runtime_version") or {"?": total_n}},
        "reviews": {"open": reviews_open, "total": reviews_total},
    }


def _repeat_usage(tid: str) -> float:
    devs = rows("SELECT device_id, COUNT(*) c FROM inference_requests WHERE tenant_id=? AND status='completed' GROUP BY device_id", (tid,))
    multi = sum(1 for d in devs if d["c"] >= 2)
    return 100 * multi / max(len(devs), 1)


def _series_sql(tid: str):
    days = rows("""SELECT substr(ts,1,10) day,
                  SUM(execution_path='local') local,
                  SUM(execution_path='cloud_simulator') cloud_simulator,
                  SUM(execution_path='queued_offline') queued_offline,
                  SUM(success=0) errors,
                  AVG(CASE WHEN success=1 AND latency_ms>0 THEN latency_ms END) avg_latency
                  FROM telemetry_events WHERE tenant_id=? GROUP BY day ORDER BY day""", (tid,))
    out = []
    for r in days:
        o = dict(r)
        o["avg_latency"] = int(o["avg_latency"] or 0)
        out.append(o)
    return out[-14:]
