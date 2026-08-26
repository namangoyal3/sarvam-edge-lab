"""On-device ASR via whisper.cpp. Same posture as the LLM: a local binary and a
local model file; nothing leaves the machine."""
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

WHISPER_BIN = os.environ.get("SARVAM_WHISPER_BIN", "whisper-cli")
WHISPER_MODEL = os.environ.get(
    "SARVAM_WHISPER_MODEL", str(Path.home() / "Models/whisper/ggml-small.bin"))


def available() -> tuple[bool, str]:
    if not shutil.which(WHISPER_BIN):
        return False, f"whisper binary '{WHISPER_BIN}' not on PATH"
    if not Path(WHISPER_MODEL).exists():
        return False, f"whisper model missing: {WHISPER_MODEL}"
    if not shutil.which("ffmpeg"):
        return False, "ffmpeg not on PATH (needed to normalise browser audio)"
    return True, f"whisper.cpp + {Path(WHISPER_MODEL).name}"


def transcribe(audio_bytes: bytes, language: str = "auto") -> dict:
    """Browser blob (webm/ogg/wav) -> 16 kHz wav -> whisper.cpp -> text."""
    ok, why = available()
    if not ok:
        raise RuntimeError(why)
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.audio"
        wav = Path(td) / "in.wav"
        src.write_bytes(audio_bytes)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(wav)],
            check=True, capture_output=True)
        out = Path(td) / "out"
        cmd = [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", str(wav),
               "--output-json", "--output-file", str(out), "--no-prints"]
        if language != "auto":
            cmd += ["-l", language]
        else:
            cmd += ["-l", "auto"]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        data = json.loads((out.with_suffix(".json")).read_text())
    text = " ".join(s["text"].strip() for s in data.get("transcription", [])).strip()
    lang = (data.get("result", {}) or {}).get("language", language)
    return {"text": text, "asr_language": lang,
            "asr_latency_ms": int((time.time() - t0) * 1000),
            "asr_model": Path(WHISPER_MODEL).name,
            "asr_runtime": "whisper.cpp (local)"}
