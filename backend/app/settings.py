import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("SARVAM_DB_PATH", str(BASE_DIR / "data" / "sarvam_edge.db"))
MODEL_PATH = os.environ.get("SARVAM_MODEL_PATH", "")          # user-provided artifact; empty => no real model
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
    return available


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
    return {"mode": "simulation", "reason": "no SARVAM_MODEL_PATH configured; deterministic fixtures are used"}
