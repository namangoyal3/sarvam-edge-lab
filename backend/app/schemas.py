from typing import Literal
from pydantic import BaseModel, Field, field_validator

Category = Literal["billing", "connectivity", "account_access", "performance",
                   "data_privacy", "security", "feature_request", "other"]
Urgency = Literal["low", "medium", "high", "critical"]
Language = Literal["en", "hi", "mixed-hi-en"]


class TriageResult(BaseModel):
    category: Category
    urgency: Urgency
    language: Language
    suggested_next_action: str = Field(min_length=3)
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=3)


class InferInput(BaseModel):
    text: str = Field(min_length=0, max_length=100_000)
    language_hint: Literal["auto", "en", "hi", "mixed-hi-en"] = "auto"
    device_id: str | None = None
    policy_id: str | None = None
    model_id: str | None = None
    force_path: Literal["local", "cloud"] | None = None


class ReviewAction(BaseModel):
    action: Literal["approve", "reject", "edit", "resolve"]
    reason: str = Field(min_length=3)
    corrected: dict | None = None   # for edit: {category?, urgency?, suggested_next_action?}


class PolicyIn(BaseModel):
    name: str
    mode: Literal["local_only", "local_preferred", "cloud_allowed", "cloud_disabled"]
    offline_queue_enabled: bool = True
    max_input_bytes: int = Field(default=4000, ge=100, le=1_000_000)
    allowed_data_classes: list[str] = ["support_text"]
    allowed_models: list[str] = []
    allowed_device_ids: list[str] = []
    min_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    hitl_risk_threshold: Literal["medium", "high", "critical"] = "high"


class DeviceEnroll(BaseModel):
    id: str | None = None
    name: str
    os: str
    ram_gb: float = Field(ge=0.5)
    cpu: str = "generic"
    gpu_npu: str = "none"
    chipset: str = "generic"
    runtime: str = "llama-cpp-python"
    tenant_id: str = "t-acme"
    never_connected: bool = False


def validate_triage(obj: dict) -> tuple[TriageResult | None, list[str]]:
    try:
        return TriageResult(**obj), []
    except Exception as e:
        errs = [f"{err['loc'][0] if err['loc'] else 'body'}: {err['msg']}" for err in getattr(e, "errors", lambda: [])()]
        return None, errs or [str(e)]
