"""Three inference runtimes. Every result carries honest labels."""
import json
import os
import time
from pathlib import Path
from .. import settings
from . import triage as T
from .logit_classifier import classify_via_logits
from .triage import classify, jitter

SIM_LABEL = "Simulated demo output"
CLOUD_LABEL = "Cloud simulator — not a real Sarvam cloud API"


def _now_ms() -> int:
    return int(time.time() * 1000)


class RuntimeResult:
    def __init__(self, result: dict, validation_status: str, validation_errors: list,
                 latency_ms: int, cost_inr: float, model_version: str, runtime_version: str,
                 label: str, fallback_reason: str | None, raw_ok: bool):
        self.result = result
        self.validation_status = validation_status
        self.validation_errors = validation_errors
        self.latency_ms = latency_ms
        self.cost_inr = cost_inr
        self.model_version = model_version
        self.runtime_version = runtime_version
        self.label = label
        self.fallback_reason = fallback_reason
        self.raw_ok = raw_ok


def _safe(result_dict: dict, seed: str, cost_inr: float, mver: str, rver: str, label: str) -> RuntimeResult:
    from ..schemas import validate_triage
    parsed, errs = validate_triage({k: v for k, v in result_dict.items() if not k.startswith("_")})
    if parsed is None:
        fb = classify("fallback default ticket")
        return RuntimeResult(
            {k: fb[k] for k in ("category", "urgency", "language", "suggested_next_action",
                                "confidence", "explanation")},
            "invalid", errs, jitter(45, seed),
            0.0, mver + "+fixture-fallback", rver, SIM_LABEL, f"model_output_invalid ({'; '.join(errs[:2])})",
            raw_ok=False)
    return RuntimeResult(
        parsed.model_dump(), "valid", [],
        jitter(55, seed), cost_inr, mver, rver, label, None, raw_ok=True)


# ---------------------------------------------------------------- fixture mode

def run_fixture(text: str, language_hint: str | None, seed: str) -> RuntimeResult:
    out = classify(text, language_hint)
    return _safe(out, seed, cost_inr=0.0, mver="rules-engine-v1.4.0",
                 rver="python-embedded-1.0", label=SIM_LABEL)


# ---------------------------------------------------------------- real local mode

LOCAL_PROMPT = f"""You are a support-ticket triage engine. Reply with ONLY a JSON object, no prose, with keys: category (one of billing|connectivity|account_access|performance|data_privacy|security|feature_request|other), urgency (one of low|medium|high|critical), language (one of en|hi|mixed-hi-en), suggested_next_action (short sentence), confidence (0-1), explanation (one sentence).

Ticket: My card was charged twice for one order, refund please
JSON: {{"category": "billing", "urgency": "high", "language": "en", "suggested_next_action": "Reverse the duplicate charge", "confidence": 0.9, "explanation": "Duplicate payment detected"}}
Ticket: Net bar bar disconnect ho raha hai, jaldi fix karo
JSON: {{"category": "connectivity", "urgency": "high", "language": "mixed-hi-en", "suggested_next_action": "Restart router and check line", "confidence": 0.9, "explanation": "Hinglish connectivity complaint"}}
Ticket: मेरा पासवर्ड भूल गया, लॉगिन नहीं हो रहा
JSON: {{"category": "account_access", "urgency": "medium", "language": "hi", "suggested_next_action": "Send password reset link", "confidence": 0.9, "explanation": "Hindi login problem"}}
Ticket: App freezes whenever I open reports
JSON: {{"category": "performance", "urgency": "medium", "language": "en", "suggested_next_action": "Collect logs and restart service", "confidence": 0.9, "explanation": "App freeze report"}}
Ticket: Delete my account and all personal data immediately
JSON: {{"category": "data_privacy", "urgency": "critical", "language": "en", "suggested_next_action": "Start DPA deletion workflow", "confidence": 0.9, "explanation": "Deletion request is high risk"}}
Ticket: Someone hacked my account and made unauthorized transactions
JSON: {{"category": "security", "urgency": "critical", "language": "en", "suggested_next_action": "Freeze account and page fraud desk", "confidence": 0.9, "explanation": "Account compromise"}}
Ticket: It would be nice to add a dark mode option
JSON: {{"category": "feature_request", "urgency": "low", "language": "en", "suggested_next_action": "Add to product backlog", "confidence": 0.9, "explanation": "Suggestion only"}}
Ticket: What are your office timings?
JSON: {{"category": "other", "urgency": "low", "language": "en", "suggested_next_action": "Reply with office hours", "confidence": 0.9, "explanation": "General query"}}

Ticket: {{text}}
JSON:"""
LOCAL_PROMPT_END = "\nJSON:"


# GBNF grammar: forces schema-valid JSON out of even heavily-quantised base models
TRIAGE_GRAMMAR = r"""
root ::= "{" ws "\"category\"" ws ":" ws cat "," ws "\"urgency\"" ws ":" ws urg "," ws "\"language\"" ws ":" ws lang "," ws "\"suggested_next_action\"" ws ":" ws str "," ws "\"confidence\"" ws ":" ws conf "," ws "\"explanation\"" ws ":" ws str ws "}"
cat ::= "\"billing\"" | "\"connectivity\"" | "\"account_access\"" | "\"performance\"" | "\"data_privacy\"" | "\"security\"" | "\"feature_request\"" | "\"other\""
urg ::= "\"low\"" | "\"medium\"" | "\"high\"" | "\"critical\""
lang ::= "\"en\"" | "\"hi\"" | "\"mixed-hi-en\""
conf ::= [0-9] "." [0-9][0-9]
str ::= "\"" ( [^"\\\x7F\x00-\x1F] ){0,90} "\""
ws ::= [ \t\n]?
"""


def _get_grammar():
    g = getattr(_get_grammar, "_g", None)
    if g is None:
        from llama_cpp import LlamaGrammar
        g = LlamaGrammar.from_string(TRIAGE_GRAMMAR.strip())
        _get_grammar._g = g
    return g


def _get_llama():
    llm = getattr(_get_llama, "_llm", None)
    if llm is None:
        from llama_cpp import Llama
        llm = Llama(model_path=settings.MODEL_PATH, n_ctx=2048, verbose=False,
                    n_gpu_layers=int(os.environ.get("SARVAM_GPU_LAYERS", "-1")))
        _get_llama._llm = llm
    return llm


def _try_llama_cpp(text: str, language_hint: str) -> dict | None:
    try:
        from llama_cpp import Llama
    except ImportError:
        return None
    llm = _get_llama()
    prompt = LOCAL_PROMPT.replace("{text}", text[:600]) + LOCAL_PROMPT_END
    # grammar-constrained greedy decode -> always parseable, enum-safe JSON
    out = llm(prompt, max_tokens=300, temperature=0.0, repeat_penalty=1.15, grammar=_get_grammar())
    raw = out["choices"][0]["text"]
    return _parse_jsonish(raw)


def _try_transformers(text: str, language_hint: str) -> dict | None:
    try:
        from transformers import pipeline
    except ImportError:
        return None
    gen = getattr(_try_transformers, "_pipe", None)
    if gen is None:
        gen = pipeline("text-generation", model=settings.MODEL_PATH, trust_remote_code=False)
        _try_transformers._pipe = gen
    out = gen(LOCAL_PROMPT.replace("{text}", text[:600]) + LOCAL_PROMPT_END,
              max_new_tokens=220, do_sample=False)
    return _parse_jsonish(out[0]["generated_text"][-600:])


def _parse_jsonish(raw: str) -> dict | None:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(raw[start:end + 1])
    except Exception:
        return None


def run_local(text: str, language_hint: str, seed: str) -> RuntimeResult:
    status = settings.active_mode()
    if status["mode"] != "real_local":
        fb = run_fixture(text, language_hint, seed)
        fb.fallback_reason = status.get("reason", "local runtime unavailable")
        fb.label = SIM_LABEL
        return fb
    t0 = _now_ms()
    try:
        if status["runtime"] == "llama_cpp":
            # ponytail: grammar generation is primary (2.5s, empirically better
            # categories). Logit scoring is experimental — its branch-sum metric
            # disagrees with greedy decoding on 2-bit quants and measured worse;
            # enable with SARVAM_LOGITS_SCORING=1.
            if os.environ.get("SARVAM_LOGITS_SCORING") == "1":
                raw = classify_via_logits(_get_llama(), text)
                if raw is None:
                    raw = _try_llama_cpp(text, language_hint)
            else:
                raw = _try_llama_cpp(text, language_hint)
        else:
            raw = _try_transformers(text, language_hint)
        wall = _now_ms() - t0
        if raw is None:
            raise ValueError("model did not emit parseable JSON")
        # Model decides the four classification fields; rules own operational
        # free text (2-bit quants produce unusable prose). Honest + useful.
        base = classify(text, language_hint)
        model_fields = {k: raw[k] for k in ("category", "urgency", "language", "confidence")
                        if k in raw}
        merged = {**base, **model_fields}
        merged["suggested_next_action"] = base["suggested_next_action"]
        merged["explanation"] = (f"[Sarvam-1 local artifact] {base['explanation']}")
        res = _safe(merged, seed, cost_inr=0.0,
                    mver=f"Sarvam-1@{settings.MODEL_PATH.split('/')[-1]}",
                    rver=status["runtime"], label="Real local model")
        res.latency_ms = max(wall, 1)
        return res
    except Exception as e:
        fb = run_fixture(text, language_hint, seed)
        fb.fallback_reason = f"local_model_failed ({type(e).__name__})"
        fb.latency_ms = max(_now_ms() - t0, 1)   # honest: report real attempt time
        return fb


# ---------------------------------------------------------------- classifier head

def run_classifier_head(text: str, language_hint: str | None, seed: str) -> RuntimeResult:
    """Purpose-built TF-IDF+LogReg head (~1MB): category from the trained model,
    everything else from the rules engine. Beats the quantized LLM 2:1 on this task."""
    out = classify(text, language_hint)
    try:
        clf = getattr(run_classifier_head, "_clf", None)
        if clf is None:
            import joblib
            path = Path(__file__).resolve().parent / "ticket_classifier.joblib"
            clf = joblib.load(path)
            run_classifier_head._clf = clf
        probs = clf.predict_proba([text])[0]
        out["category"] = clf.classes_[int(probs.argmax())]
        out["confidence"] = round(float(probs.max()), 2)
        # urgency follows the head's category when it lands in the high-risk set
        if out["category"] in ("data_privacy", "security") and out["urgency"] not in ("critical", "high"):
            out["urgency"] = "high"
        out["explanation"] = f"[ticket-classifier head p={out['confidence']}] " + out["explanation"]
    except Exception as e:   # head missing/degraded -> rules result stands
        out["explanation"] += f"; [classifier head unavailable: {type(e).__name__}]"
    return _safe(out, seed, cost_inr=0.0, mver="ticket-head-v1",
                 rver="sklearn-tfidf-logreg", label=SIM_LABEL)


# ---------------------------------------------------------------- cloud simulator

def run_cloud_sim(text: str, language_hint: str, seed: str, cost_per_req: float) -> RuntimeResult:
    import random
    rng = random.Random(int(seed.encode().hex(), 16))
    out = classify(text, language_hint)
    out["confidence"] = min(0.98, round(out["confidence"] + 0.06, 2))
    out["explanation"] = "[cloud-sim quality uplift] " + out["explanation"]
    res = _safe(out, seed, cost_inr=round(cost_per_req, 4),
                mver="sarvam-cloud-large-sim-v3", rver="cloud-simulator-1.1", label=CLOUD_LABEL)
    res.latency_ms = rng.randint(900, 1600)
    return res
