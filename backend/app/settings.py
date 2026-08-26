import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("SARVAM_DB_PATH", str(BASE_DIR / "data" / "sarvam_edge.db"))
MODEL_PATH = os.environ.get("SARVAM_MODEL_PATH", "")          # user-provided artifact; empty => no real model
MODEL_ID = os.environ.get("SARVAM_MODEL_ID", "")               # catalog id of that artifact; drives UI defaults
SEED_HISTORY = os.environ.get("SARVAM_SEED_HISTORY", "1") == "1"  # 0 => dashboards show only real traffic
RUNTIME_PREF = os.environ.get("SARVAM_RUNTIME", "auto")        # auto | llama_cpp | transformers | fixture
CONTENT_LOGGING = os.environ.get("DEMO_CONTENT_LOGGING", "0") == "1"
POLICY_FRESHNESS_MINUTES = int(os.environ.get("POLICY_FRESHNESS_MINUTES", "60"))
MAX_INPUT_BYTES_DEFAULT = 4000
HOST = os.environ.get("SARVAM_HOST", "127.0.0.1")
PORT = int(os.environ.get("SARVAM_PORT", "8000"))
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

APP_VERSION = "0.9.0-demo"


def runtime_status() -> dict:
    """Which real local runtimes can actually load MODEL_PATH right now."""
    available = {}
    if MODEL_PATH:
        try:
            import llama_cpp  # noqa: F401
            available["llama_cpp"] = True
        except ImportError:
            available["llama_cpp"] = False
        try:
            import transformers  # noqa: F401
            available["transformers"] = True
        except ImportError:
            available["transformers"] = False
    else:
        available["llama_cpp"] = False
        available["transformers"] = False
    # The classifier head is a real trained model too, and it does NOT come
    # from MODEL_PATH -- it ships inside the image. run_classifier_head catches
    # every exception so a degraded head still answers, which meant a missing
    # scikit-learn served rules-engine output under the head's name with only a
    # note buried in `explanation`. Report it where the answer is visible.
    available["classifier_head"] = _classifier_head_ready()
    return available


def _classifier_head_ready() -> bool:
    """Both the deps and the artifact, since either one alone is useless."""
    try:
        import joblib  # noqa: F401
        import sklearn  # noqa: F401
    except ImportError:
        return False
    # Next to this module, the same way run_classifier_head resolves it.
    # BASE_DIR is settings.py's GRANDparent (backend/, /app in the image), so
    # building the path from it silently missed the file in both layouts.
    return (Path(__file__).resolve().parent / "engine" / "ticket_classifier.joblib").exists()


def active_mode() -> dict:
    """The honest answer to 'what will inference do right now'."""
    if MODEL_PATH and Path(MODEL_PATH).exists():
        rs = runtime_status()
        if RUNTIME_PREF in ("llama_cpp", "auto") and rs["llama_cpp"]:
            rt = "llama_cpp"
        elif RUNTIME_PREF in ("transformers", "auto") and rs["transformers"]:
            rt = "transformers"
        else:
            return {"mode": "fixture_fallback", "reason": f"model path set but no compatible runtime installed (tried: {RUNTIME_PREF})"}
        return {"mode": "real_local", "runtime": rt}
    if MODEL_PATH:
        return {"mode": "fixture_fallback", "reason": "SARVAM_MODEL_PATH is set but the file does not exist"}
    # No GGUF does not mean no model. The classifier head is trained weights
    # doing real inference, and reporting "simulation" over it told the viewer
    # the opposite of the truth.
    if _classifier_head_ready():
        return {"mode": "real_local", "runtime": "classifier_head",
                "reason": "no GGUF configured; the ~1MB trained ticket-classifier head serves m-ticket-head"}
    return {"mode": "simulation", "reason": "no SARVAM_MODEL_PATH configured; deterministic fixtures are used"}
