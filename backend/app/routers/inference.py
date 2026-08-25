from fastapi import APIRouter, Depends, HTTPException

from ..common import ctx
from ..db import row, rows
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
