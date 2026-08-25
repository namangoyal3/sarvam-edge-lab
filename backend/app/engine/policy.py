"""Policy evaluation. Runs BEFORE inference. Never silently routes to cloud."""
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Decision:
    def __init__(self, outcome: str, reasons: list[str]):
        self.outcome = outcome          # run_local | run_cloud | queue_offline | human_review | rejected
        self.reasons = reasons

    def to_dict(self):
        return {"outcome": self.outcome, "reasons": self.reasons}


def evaluate(policy: dict, text: str, ctx: dict) -> Decision:
    """ctx: {network_online, local_available, model_id, device_id, data_class, category_hint?}"""
    p = policy
    reasons = []

    if len(text.encode()) > p["max_input_bytes"]:
        return Decision("rejected", [f"input size {len(text.encode())}B exceeds policy max {p['max_input_bytes']}B"])

    dc = ctx.get("data_class", "support_text")
    allowed_dc = __import__("json").loads(p["allowed_data_classes"]) if isinstance(p["allowed_data_classes"], str) else p["allowed_data_classes"]
    if allowed_dc and dc not in allowed_dc:
        return Decision("rejected", [f"data class '{dc}' not permitted by policy"])

    am = __import__("json").loads(p["allowed_models"]) if isinstance(p["allowed_models"], str) else p["allowed_models"]
    mid = ctx.get("model_id")
    if am and mid and mid not in am:
        return Decision("rejected", [f"model '{mid}' is not in the policy allow-list"])

    ad = __import__("json").loads(p["allowed_device_ids"]) if isinstance(p["allowed_device_ids"], str) else p["allowed_device_ids"]
    did = ctx.get("device_id")
    if ad and did and did not in ad:
        return Decision("rejected", [f"device '{did}' not enrolled for this policy"])

    cloud_prohibited = p["mode"] in ("local_only", "cloud_disabled")
    local_ok = bool(ctx.get("local_available"))
    online = bool(ctx.get("network_online"))

    if ctx.get("force_path") == "cloud":
        if cloud_prohibited:
            return _no_cloud_exit(p, online, ["explicit cloud path requested but policy prohibits cloud"])
        if not online:
            return _offline_exit(p, ["explicit cloud requested while network offline"])
        return Decision("run_cloud", ["cloud explicitly forced; policy mode allows it"])

    if local_ok:
        return Decision("run_local", [f"policy mode={p['mode']}; local execution available and preferred"])

    if cloud_prohibited:
        return _no_cloud_exit(p, online, [f"local unavailable and policy mode={p['mode']} prohibits cloud"])

    if not online:
        return _offline_exit(p, ["network offline; cloud path unreachable"])

    return Decision("run_cloud", ["local unavailable; policy permits cloud fallback"])


def _no_cloud_exit(policy, online, why) -> Decision:
    if policy["offline_queue_enabled"] and not online:
        return Decision("queue_offline", why + ["queued per offline_queue_enabled=true"])
    return Decision("human_review", why + ["routing to human review instead of cloud (policy-safe exit)"])


def _offline_exit(policy, why) -> Decision:
    if policy["offline_queue_enabled"]:
        return Decision("queue_offline", why + ["queued until reconnect"])
    return Decision("rejected", why + ["offline queue disabled by policy"])


def needs_hitl(result_conf: float, category: str, validation_ok: bool, policy: dict,
               stale_offline: bool) -> tuple[bool, str]:
    if not validation_ok:
        return True, "invalid_output"
    min_c = policy["min_confidence"]
    if result_conf < min_c:
        return True, "low_confidence"
    thr = policy["hitl_risk_threshold"]
    if RISK_ORDER.get(category, 0) >= RISK_ORDER.get(thr, 2):
        return True, "high_risk"
    if stale_offline:
        return True, "stale_offline"
    return False, ""
