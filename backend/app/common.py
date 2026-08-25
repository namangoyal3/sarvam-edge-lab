"""Shared request context (demo RBAC), audit + telemetry writers, network state."""
import json
from fastapi import Header, HTTPException

from . import seed
from . import settings as _settings
from .db import db, row, rows, tx, jdump
from .engine import triage as T

settings = _settings

ROLE_RANK = {"viewer": 0, "reviewer": 1, "admin": 2}
QUEUE_LIMIT = 500


def ctx(x_demo_role: str = Header(default="admin"), x_tenant_id: str = Header(default="t-acme")):
    user = row("SELECT * FROM users WHERE role=? AND tenant_id=? ORDER BY role DESC",
               (x_demo_role, x_tenant_id))
    return {"role": x_demo_role if x_demo_role in ROLE_RANK else "admin",
            "tenant_id": x_tenant_id,
            "user_id": user["id"] if user else "u-naman"}


def require(ctxinfo: dict, minimum: str):
    if ROLE_RANK[ctxinfo["role"]] < ROLE_RANK[minimum]:
        raise HTTPException(403, f"demo RBAC: role '{ctxinfo['role']}' cannot perform this action (needs {minimum})")


def network_online() -> bool:
    from .db import get_setting
    return get_setting("network_online", "1") == "1"


def content_logging() -> bool:
    from .db import get_setting
    return get_setting("content_logging", "1" if settings.CONTENT_LOGGING else "0") == "1"


def policy_stale_minutes() -> float:
    p = row("SELECT MAX(last_synced_at) m FROM policies")
    if not p or not p["m"]:
        return 9999.0
    dt = datetime_diff_min(p["m"])
    return dt


def datetime_diff_min(iso: str) -> float:
    from datetime import datetime, timezone
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 60
    except Exception:
        return 9999.0


def is_policy_stale() -> bool:
    return network_online() is False and policy_stale_minutes() > settings.POLICY_FRESHNESS_MINUTES


def guard_high_risk_action(ctxinfo):
    """Update/rollback/policy-change are restricted while offline beyond freshness window."""
    require(ctxinfo, "admin")
    if is_policy_stale():
        raise HTTPException(
            409,
            f"STALE_POLICY: device has been offline {policy_stale_minutes():.0f} min "
            f"(freshness limit {settings.POLICY_FRESHNESS_MINUTES} min). High-risk management actions are "
            "restricted until reconnect + policy resync.")


def audit(action: str, *, ctxinfo=None, device_id=None, policy_version=None, model_version=None,
          approval_status=None, correlation_id=None, reason=None, result_summary=None):
    eid = seed.rid("aud")
    ci = ctxinfo or {}
    db().execute("""INSERT INTO audit_events(id,ts,actor_user,role,tenant_id,device_id,policy_version,
                  model_version,action,approval_status,correlation_id,reason,result_summary)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (eid, seed.utcnow(), ci.get("user_id"), ci.get("role"), ci.get("tenant_id"),
                  device_id, policy_version, model_version, action, approval_status,
                  correlation_id, reason, result_summary))
    db().commit()
    return eid


def telemetry(*, tenant_id, event_id=None, device_id=None, correlation_id=None, model_version=None,
              runtime_version=None, policy_version=1, execution_path="local", latency_ms=0,
              success=True, error_code=None, fallback_reason=None, confidence=None,
              input_bytes=0, output_bytes=0, queue_state="-", text=None, generated=False) -> str:
    eid = event_id or seed.rid("evt")
    preview = (text[:120] if text else None) if content_logging() else None  # noqa: F841
    online = network_online()
    with tx():
        db().execute("""INSERT INTO telemetry_events(event_id,ts,tenant_id,device_id,correlation_id,
                      model_version,runtime_version,policy_version,execution_path,latency_ms,success,
                      error_code,fallback_reason,confidence,input_bytes,output_bytes,queue_state,synced,
                      content_preview,is_generated)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (eid, seed.utcnow(), tenant_id, device_id, correlation_id, model_version,
                      runtime_version, policy_version, execution_path, latency_ms,
                      1 if success else 0, error_code, fallback_reason, confidence,
                      input_bytes, output_bytes,
                      ("pending_sync" if not online else "-"),
                      1 if online else 0, preview, 1 if generated else 0))
        if not online:
            enqueue("telemetry_sync", {"event_id": eid}, key=eid)
    return eid


def enqueue(payload_type: str, payload: dict, key: str | None = None):
    key = key or payload.get("idempotency_key") or seed.rid("idem")
    n = db().execute("SELECT COUNT(*) c FROM offline_queue WHERE state IN ('pending','in_flight')").fetchone()["c"]
    dropped = 0
    if n >= QUEUE_LIMIT:   # bounded queue: drop oldest pending, keep audit note
        oldest = db().execute(
            "SELECT id FROM offline_queue WHERE state='pending' ORDER BY id LIMIT 1").fetchone()
        if oldest:
            db().execute("DELETE FROM offline_queue WHERE id=?", (oldest["id"],))
            dropped += 1
    db().execute("""INSERT INTO offline_queue(idempotency_key,payload_type,payload,state,next_attempt_at,created_at)
                  VALUES(?,?,?, 'pending', ?, ?)
                  ON CONFLICT(idempotency_key) DO NOTHING""",
                 (key, payload_type, jdump(payload), seed.utcnow(), seed.utcnow()))
    return {"key": key, "dropped_oldest": dropped}
