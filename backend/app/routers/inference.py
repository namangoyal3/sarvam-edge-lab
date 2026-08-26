from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from ..common import ctx
from ..db import row, rows
from ..engine import asr
from ..pipeline import run_pipeline
from ..schemas import InferInput

router = APIRouter(tags=["inference"])


@router.post("/inference")
def post_inference(inp: InferInput, ctxinfo: dict = Depends(ctx)):
    try:
        return run_pipeline(inp, ctxinfo)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/inference/{request_id}")
def get_inference(request_id: str):
    r = row("SELECT * FROM inference_requests WHERE id=?", (request_id,))
    if not r:
        raise HTTPException(404, "request not found")
    results = rows("SELECT * FROM inference_results WHERE request_id=? ORDER BY version", (request_id,))
    review = row("SELECT id,status,reason_code FROM review_tasks WHERE request_id=?", (request_id,))
    return {"request": r, "results": results, "review_task": review}


@router.get("/inference/voice/status")
def voice_status():
    ok, detail = asr.available()
    return {"available": ok, "detail": detail}


@router.post("/inference/voice")
async def post_voice(audio: UploadFile = File(...),
                     device_id: str | None = Form(None),
                     policy_id: str | None = Form(None),
                     model_id: str | None = Form(None),
                     ctxinfo: dict = Depends(ctx)):
    """Spoken ticket -> on-device whisper.cpp -> the normal triage pipeline.
    Both models run locally; the request never needs a network."""
    blob = await audio.read()
    if len(blob) > 15_000_000:
        raise HTTPException(413, "audio too large (15MB cap)")
    try:
        # whisper.cpp + ffmpeg are synchronous; keep them off the event loop
        tr = await run_in_threadpool(asr.transcribe, blob)
    except RuntimeError as e:
        raise HTTPException(503, f"on-device ASR unavailable: {e}")
    except Exception as e:
        raise HTTPException(422, f"could not transcribe audio: {type(e).__name__}")
    if not tr["text"]:
        raise HTTPException(422, "no speech detected")
    inp = InferInput(text=tr["text"], device_id=device_id or None,
                     policy_id=policy_id or None, model_id=model_id or None)
    try:
        resp = run_pipeline(inp, ctxinfo)
    except ValueError as e:
        raise HTTPException(404, str(e))
    resp["voice"] = tr
    resp["trace"].insert(0, {"step": "asr_transcription",
                             "detail": f"{tr['asr_model']} via {tr['asr_runtime']}; "
                                       f"lang={tr['asr_language']}; {tr['asr_latency_ms']}ms; "
                                       f"audio never left the device"})
    return resp
