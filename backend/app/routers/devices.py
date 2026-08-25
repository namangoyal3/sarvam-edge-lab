from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from ..common import ctx, require, guard_high_risk_action, audit, telemetry, network_online, is_policy_stale
from ..db import db, row, rows, tx, jload, jdump
from ..engine import compat as C
from ..pipeline import drain_inference_queue
from ..schemas import DeviceEnroll
from ..seed import rid, utcnow

router = APIRouter(prefix="/devices", tags=["devices"])


def _with_compat(d: dict) -> dict:
    model = row("SELECT * FROM models WHERE id=?", (d["model_id"],)) if d["model_id"] else None
    d["compatibility_detail"] = C.check(d, model) if model else {"status": "unknown", "reasons": ["no model assigned"]}
    return d


@router.get("")
def list_devices(tenant_id: str | None = None, ctxinfo: dict = Depends(ctx)):
    tid = tenant_id or ctxinfo["tenant_id"]
    out = [_with_compat(d) for d in rows("SELECT * FROM devices WHERE tenant_id=? ORDER BY id", (tid,))]
    return out


@router.post("/enroll")
def enroll(dev: DeviceEnroll, ctxinfo: dict = Depends(ctx)):
    require(ctxinfo, "admin")
    did = dev.id or rid("DEV").replace("DEV_", "DEV-")
    if row("SELECT 1 FROM devices WHERE id=?", (did,)):
        raise HTTPException(409, f"device {did} already enrolled")
    with tx() as c:
        c.execute("""INSERT INTO devices(id,tenant_id,name,os,ram_gb,cpu,gpu_npu,chipset,runtime,
                    policy_id,status,battery_pct,thermal,last_heartbeat,compatibility,update_status,
                    never_connected,enrolled_at)
                    VALUES(?,?,?,?,?,?,?,?,?,'p-balanced','online',85,'nominal',?, 'unknown','up_to_date',?,?)""",
                   (did, dev.tenant_id, dev.name, dev.os, dev.ram_gb, dev.cpu, dev.gpu_npu,
                    dev.chipset, dev.runtime, None if dev.never_connected else utcnow(),
                    1 if dev.never_connected else 0, utcnow()))
    audit("device.enroll", ctxinfo=ctxinfo, device_id=did, reason=f"os={dev.os} ram={dev.ram_gb}GB",
          result_summary="enrolled")
    return _with_compat(row("SELECT * FROM devices WHERE id=?", (did,)))


def _get(did: str) -> dict:
    d = row("SELECT * FROM devices WHERE id=?", (did,))
    if not d:
        raise HTTPException(404, f"device {did} not found")
    return d


@router.post("/{device_id}/heartbeat")
def heartbeat(device_id: str, ctxinfo: dict = Depends(ctx)):
    d = _get(device_id)
    if d["status"] == "disabled":
        raise HTTPException(409, "device disabled; heartbeat refused")
    with tx():
        from ..db import db
        import random
        rng = random.Random(f"{device_id}{utcnow()[:13]}")
        db().execute("UPDATE devices SET last_heartbeat=?, status=CASE WHEN status='offline' THEN 'offline' ELSE 'online' END, "
                   "battery_pct=?, thermal=? WHERE id=?",
                   (utcnow(), max(5, min(100, (d["battery_pct"] or 80) + rng.randint(-3, 3))),
                    "elevated" if rng.random() < 0.1 else "nominal", device_id))
    return _get(device_id)


@router.post("/{device_id}/offline")
def go_offline(device_id: str, ctxinfo: dict = Depends(ctx)):
    require(ctxinfo, "admin")
    _get(device_id)
    with tx() as c:
        c.execute("UPDATE devices SET status='offline' WHERE id=?", (device_id,))
    audit("device.offline", ctxinfo=ctxinfo, device_id=device_id, reason="admin action")
    return _get(device_id)


@router.post("/{device_id}/reconnect")
def reconnect(device_id: str, ctxinfo: dict = Depends(ctx)):
    require(ctxinfo, "admin")
    _get(device_id)
    from ..db import set_setting
    set_setting("network_online", "1")   # in this lab, a device reconnect restores the simulated network
    with tx() as c:
        c.execute("UPDATE devices SET status='online', never_connected=0, last_heartbeat=?, update_status='up_to_date' WHERE id=?",
                   (utcnow(), device_id))
        # T3: policy resync scoped to THIS device's tenant, not all tenants
        c.execute("""UPDATE policies SET last_synced_at=? WHERE tenant_id=
                  (SELECT tenant_id FROM devices WHERE id=?)""", (utcnow(), device_id))
        # idempotent telemetry sync + drain queued inference jobs
        synced = 0
        for q in rows("SELECT * FROM offline_queue WHERE state IN ('pending','failed') AND payload_type='telemetry_sync'"):
            p = jload(q["payload"])
            dup = c.execute("SELECT 1 FROM telemetry_events WHERE event_id=? AND synced=1",
                             (p.get("event_id", ""),)).fetchone()
            if not dup:
                db().execute("UPDATE telemetry_events SET synced=1, queue_state='synced' WHERE event_id=?",
                           (p.get("event_id", ""),))
            else:
                pass  # duplicate: skip silently, counted below
            db().execute("INSERT INTO offline_queue(idempotency_key,payload_type,payload,state,attempts,created_at) "
                       "VALUES(?,?,?,'synced',?,?) ON CONFLICT(idempotency_key) DO UPDATE SET state='synced'",
                       (q["idempotency_key"], q["payload_type"], q["payload"], q["attempts"] + 1, utcnow()))
            synced += 1
    drained = drain_inference_queue()
    audit("device.reconnect", ctxinfo=ctxinfo, device_id=device_id,
          result_summary=f"telemetry_synced={synced} queued_jobs_executed={drained}")
    return {**_get(device_id), "telemetry_synced": synced, "queued_jobs_executed": drained}


@router.post("/{device_id}/update")
def update_model(device_id: str, target_model_id: str = "m-triage-rules-sim",
                 target_version: str = "1.5.0", ctxinfo: dict = Depends(ctx)):
    guard_high_risk_action(ctxinfo)
    d = _get(device_id)
    if not network_online():
        raise HTTPException(409, "model updates require the simulated network to be online")
    m = row("SELECT * FROM models WHERE id=?", (target_model_id,))
    if not m:
        raise HTTPException(404, f"model {target_model_id} not found")
    dep = rid("dep")
    with tx() as c:
        c.execute("INSERT INTO deployments VALUES(?,?,?,?,?,'staged','complete',?)",
                   (dep, target_model_id, d["model_version"], target_version, jdump([device_id]), utcnow()))
        db().execute("""INSERT INTO update_rollouts VALUES(?,?,?,?,?,?,'success',?)""",
                   (rid("ro"), device_id, dep, "update", d["model_version"], target_version, utcnow()))
        db().execute("UPDATE devices SET model_id=?, model_version=?, update_status='up_to_date' WHERE id=?",
                   (target_model_id, target_version, device_id))
    audit("device.model_update", ctxinfo=ctxinfo, device_id=device_id, model_version=target_version,
          approval_status="auto", result_summary=f"{d['model_version']} -> {target_version}")
    return _with_compat(_get(device_id))


@router.post("/{device_id}/rollback")
def rollback(device_id: str, ctxinfo: dict = Depends(ctx)):
    guard_high_risk_action(ctxinfo)
    d = _get(device_id)
    prev = row("""SELECT * FROM update_rollouts WHERE device_id=? AND kind='update'
               ORDER BY created_at DESC LIMIT 1 OFFSET 0""", (device_id,))
    prev_ver = (prev["from_version"] if prev and prev["from_version"] else "1.3.2")
    prev_model = d["model_id"]
    with tx() as c:
        c.execute("""INSERT INTO update_rollouts VALUES(?,?,?,?,?,?,'success',?)""",
                   (rid("ro"), device_id, None, "rollback", d["model_version"], prev_ver, utcnow()))
        db().execute("UPDATE devices SET model_version=?, update_status='rolled_back' WHERE id=?",
                   (prev_ver, device_id))
    audit("device.model_rollback", ctxinfo=ctxinfo, device_id=device_id, model_version=prev_ver,
          result_summary=f"rolled back {d['model_version']} -> {prev_ver}")
    return _with_compat(_get(device_id))


@router.post("/{device_id}/policy")
def assign_policy(device_id: str, policy_id: str = "p-balanced", ctxinfo: dict = Depends(ctx)):
    require(ctxinfo, "reviewer")
    _get(device_id)
    if not row("SELECT 1 FROM policies WHERE id=?", (policy_id,)):
        raise HTTPException(404, f"policy {policy_id} not found")
    with tx() as c:
        c.execute("UPDATE devices SET policy_id=? WHERE id=?", (policy_id, device_id))
    audit("device.policy_assigned", ctxinfo=ctxinfo, device_id=device_id,
          result_summary=f"policy={policy_id}")
    return _get(device_id)


@router.post("/{device_id}/disable")
def disable_device(device_id: str, ctxinfo: dict = Depends(ctx)):
    require(ctxinfo, "admin")
    _get(device_id)
    with tx() as c:
        c.execute("UPDATE devices SET status='disabled' WHERE id=?", (device_id,))
    audit("device.disable", ctxinfo=ctxinfo, device_id=device_id, reason="admin action")
    return _get(device_id)


@router.get("/{device_id}/diagnostics")
def diagnostics(device_id: str):
    """Local diagnostic bundle. Works for never-connected devices too."""
    d = _get(device_id)
    telem = rows("SELECT * FROM telemetry_events WHERE device_id=? ORDER BY ts DESC LIMIT 50", (device_id,))
    rollouts = rows("SELECT * FROM update_rollouts WHERE device_id=? ORDER BY created_at DESC LIMIT 10", (device_id,))
    model = row("SELECT * FROM models WHERE id=?", (d["model_id"],)) if d["model_id"] else None
    bundle = {
        "bundle_type": "local_diagnostic_export",
        "generated_at": utcnow(),
        "device": d,
        "assigned_model": {k: model[k] for k in ("id", "name", "version", "quantization")} if model else None,
        "compatibility": C.check(d, model) if model else None,
        "recent_rollouts": rollouts,
        "recent_telemetry_local_only": len(telem),
        "note_central_analytics": (
            "Device has NEVER connected centrally: real-time central analytics are unavailable. "
            "This bundle is the offline diagnostic export." if d["never_connected"]
            else "Central analytics available when network online."),
        "privacy": "No raw ticket content included.",
    }
    return JSONResponse(bundle, headers={"Content-Disposition": f'attachment; filename="{device_id}-diagnostics.json"'})
