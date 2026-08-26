from fastapi import APIRouter, Body, Depends

from .. import settings
from ..common import ctx, require, network_online, content_logging, is_policy_stale, policy_stale_minutes, audit
from ..db import get_setting, set_setting
from ..seed import utcnow

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    mode = settings.active_mode()
    return {
        "status": "ok",
        "app_version": settings.APP_VERSION,
        "mode": mode["mode"],
        "mode_reason": mode.get("reason", "real local model loaded"),
        "model_path": settings.MODEL_PATH or "(none)",
        "model_id": settings.MODEL_ID or None,
        "runtime_preference": settings.RUNTIME_PREF,
        "network_online": network_online(),
        "policy_stale": is_policy_stale(),
        "policy_age_min": round(policy_stale_minutes(), 1),
        "content_logging": content_logging(),
        "disclaimer": "Demo build; simulated outputs are not Sarvam Edge benchmarks.",
    }


@router.post("/system/network")
def set_network(online: bool = Body(..., embed=True), ctxinfo: dict = Depends(ctx)):
    prev = network_online()
    set_setting("network_online", "1" if online else "0")
    if not online:
        # policy freshness clock effectively starts now; record sync marker semantics
        pass
    audit("system.network_toggle", ctxinfo=ctxinfo, reason=f"{prev} -> {online}",
          result_summary="global simulated network switch")
    return {"online": online, "changed_at": utcnow()}


@router.get("/system/settings")
def get_settings_view(ctxinfo: dict = Depends(ctx)):
    return {
        "network_online": network_online(),
        "content_logging": content_logging(),
        "policy_freshness_limit_min": settings.POLICY_FRESHNESS_MINUTES,
        "policy_stale": is_policy_stale(),
    }


@router.post("/system/content-logging")
def toggle_content_logging(enabled: bool = Body(..., embed=True), ctxinfo: dict = Depends(ctx)):
    require(ctxinfo, "admin")
    set_setting("content_logging", "1" if enabled else "0")
    audit("system.content_logging", ctxinfo=ctxinfo, reason="demo toggle",
          result_summary=f"content_logging={'on' if enabled else 'off'}")
    return {"content_logging": enabled}
