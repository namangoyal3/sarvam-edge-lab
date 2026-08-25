from fastapi import APIRouter, Depends, HTTPException

from ..common import ctx, require, guard_high_risk_action, audit
from ..db import row, rows, tx, jdump
from ..engine import compat as C
from ..schemas import PolicyIn
from ..seed import rid, utcnow

router = APIRouter(tags=["catalog"])


# ------------------------------------------------------------------ models

@router.get("/models")
def list_models(device_id: str | None = None):
    out = []
    dev = row("SELECT * FROM devices WHERE id=?", (device_id,)) if device_id else None
    for m in rows("SELECT * FROM models ORDER BY id"):
        d = {**m,
             "supported_os": jdump_parse(m["supported_os"]),
             "supported_chipsets": jdump_parse(m["supported_chipsets"]),
             "supported_runtimes": jdump_parse(m["supported_runtimes"])}
        if dev:
            d["compatibility"] = C.check(dev, m)
        out.append(d)
    return out


def jdump_parse(s):
    import json
    return json.loads(s) if s else []


@router.post("/models/register")
def register_model(body: dict, ctxinfo: dict = Depends(ctx)):
    require(ctxinfo, "admin")
    mid = body.get("id") or rid("m")
    if row("SELECT 1 FROM models WHERE id=?", (mid,)):
        raise HTTPException(409, "model id exists")
    with tx() as c:
        c.execute("""INSERT INTO models(id,name,task,param_count,artifact_size_mb,precision,quantization,
                    runtime,supported_os,supported_chipsets,supported_runtimes,min_ram_gb,recommended_ram_gb,
                    expected_latency_ms,version,release_status,checksum,signature,kind,registered_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (mid, body.get("name", "unnamed"), body.get("task", "text-generation"),
                    body.get("param_count"), body.get("artifact_size_mb"), body.get("precision", "int4"),
                    body.get("quantization", "Q4_K_M"), body.get("runtime", "llama.cpp family"),
                    jdump(body.get("supported_os", ["linux"])), jdump(body.get("supported_chipsets", [])),
                    jdump(body.get("supported_runtimes", ["llama-cpp-python"])),
                    body.get("min_ram_gb", 4), body.get("recommended_ram_gb"),
                    body.get("expected_latency_ms", 500), body.get("version", "0.1.0"),
                    body.get("release_status", "registered_demo"), body.get("checksum"),
                    body.get("signature", "unsigned-user-provided"), body.get("kind", "local"), utcnow()))
    audit("model.register", ctxinfo=ctxinfo, model_version=body.get("version"),
          result_summary=f"model={mid}")
    return row("SELECT * FROM models WHERE id=?", (mid,))


# ------------------------------------------------------------------ policies

@router.get("/policies")
def list_policies(tenant_id: str | None = None, ctxinfo: dict = Depends(ctx)):
    tid = tenant_id or ctxinfo["tenant_id"]
    return [jparse_policy(p) for p in rows(
        "SELECT * FROM policies WHERE tenant_id=? ORDER BY id", (tid,))]


def jparse_policy(p):
    p = dict(p)
    for k in ("allowed_data_classes", "allowed_models", "allowed_device_ids"):
        p[k] = jdump_parse(p[k])
    p["offline_queue_enabled"] = bool(p["offline_queue_enabled"])
    return p


@router.post("/policies")
def upsert_policy(p: PolicyIn, ctxinfo: dict = Depends(ctx)):
    guard_high_risk_action(ctxinfo)
    existing = row("SELECT * FROM policies WHERE name=? AND tenant_id=?", (p.name, ctxinfo["tenant_id"]))
    pid = existing["id"] if existing else rid("p")
    version = (existing["version"] + 1) if existing else 1
    with tx() as c:
        c.execute("""INSERT INTO policies(id,tenant_id,name,mode,offline_queue_enabled,max_input_bytes,
                    allowed_data_classes,allowed_models,allowed_device_ids,min_confidence,hitl_risk_threshold,
                    version,last_synced_at,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET mode=excluded.mode, offline_queue_enabled=excluded.offline_queue_enabled,
                      max_input_bytes=excluded.max_input_bytes, allowed_data_classes=excluded.allowed_data_classes,
                      allowed_models=excluded.allowed_models, allowed_device_ids=excluded.allowed_device_ids,
                      min_confidence=excluded.min_confidence, hitl_risk_threshold=excluded.hitl_risk_threshold,
                      version=excluded.version, last_synced_at=excluded.last_synced_at""",
                   (pid, ctxinfo["tenant_id"], p.name, p.mode, int(p.offline_queue_enabled),
                    p.max_input_bytes, jdump(p.allowed_data_classes), jdump(p.allowed_models),
                    jdump(p.allowed_device_ids), p.min_confidence, p.hitl_risk_threshold,
                    version, utcnow(), utcnow()))
    audit("policy.upsert", ctxinfo=ctxinfo, policy_version=version,
          result_summary=f"policy={pid} mode={p.mode} v{version}")
    return jparse_policy(row("SELECT * FROM policies WHERE id=?", (pid,)))
