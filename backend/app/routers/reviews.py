from fastapi import APIRouter, Depends, HTTPException

from ..common import ctx, require, audit
from ..db import db, row, rows, tx, jload, jdump
from ..schemas import ReviewAction
from ..seed import utcnow, rid

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("")
def list_reviews(status: str | None = None):
    sql = "SELECT * FROM review_tasks"
    params: tuple = ()
    if status:
        sql += " WHERE status=?"
        params = (status,)
    sql += " ORDER BY created_at DESC LIMIT 100"
    out = []
    for r in rows(sql, params):
        r["original_result"] = jload(r["original_result"])
        r["resolved_result"] = jload(r["resolved_result"])
        trail = rows("SELECT * FROM audit_events WHERE correlation_id=? ORDER BY ts", (r["correlation_id"],)) \
            if r["correlation_id"] else []
        r["audit_trail"] = [{"ts": a["ts"], "action": a["action"], "actor": a["actor_user"],
                             "role": a["role"], "approval_status": a["approval_status"],
                             "reason": a["reason"]} for a in trail]
        out.append(r)
    return out


@router.post("/{review_id}/action")
def act(review_id: str, body: ReviewAction, ctxinfo: dict = Depends(ctx)):
    require(ctxinfo, "reviewer")
    rv = row("SELECT * FROM review_tasks WHERE id=?", (review_id,))
    if not rv:
        raise HTTPException(404, "review task not found")
    if rv["status"] != "open":
        raise HTTPException(409, f"task already {rv['status']}")

    original = jload(rv["original_result"]) or {}
    new_status, resolved_result, approval = None, None, None
    if body.action == "approve":
        new_status, resolved_result, approval = "resolved", original, "approved"
    elif body.action == "reject":
        new_status, resolved_result, approval = "rejected", original, "rejected"
    elif body.action == "edit":
        corrected = {**original}
        for k in ("category", "urgency", "suggested_next_action"):
            if k in (body.corrected or {}):
                corrected[k] = body.corrected[k]
        # edited results are versioned; confidence drops to reviewer-authority value
        corrected["confidence"] = 1.0
        corrected["explanation"] = (original.get("explanation", "") +
                                    " | [edited by human reviewer]")
        new_status, resolved_result, approval = "resolved", corrected, "edited_approved"
        with tx():
            from ..db import db
            req = row("SELECT id FROM inference_requests WHERE id=?", (rv["request_id"],))
            if req:
                maxv = row("SELECT MAX(version) m FROM inference_results WHERE request_id=?",
                           (rv["request_id"],))["m"] or 1
                db().execute("""INSERT INTO inference_results(id,request_id,version,category,urgency,language,
                            suggested_next_action,confidence,explanation,model_version,runtime_version,created_at)
                            SELECT ?,?,MAX(version)+1,category,urgency,language,suggested_next_action,
                            ?,?,?,model_version,runtime_version,? FROM inference_results
                            WHERE request_id=?""",
                           (rid("res"), rv["request_id"], corrected["confidence"],
                            corrected["explanation"], utcnow(), rv["request_id"]))
                db().execute("""UPDATE inference_results SET superseded_by=? WHERE request_id=? AND version=(SELECT MAX(version)-0 FROM inference_results) """,
                           ("superseded_by_review_edit", rv["request_id"])) if False else None
                db().execute("UPDATE inference_requests SET status='completed' WHERE id=?", (rv["request_id"],))
    elif body.action == "resolve":
        new_status, resolved_result, approval = "resolved", original, "resolved_no_change"

    with tx() as c:
        c.execute("""UPDATE review_tasks SET status=?, reviewer_id=?, resolution_note=?, resolved_result=?,
                    resolved_at=? WHERE id=?""",
                   (new_status, ctxinfo["user_id"], body.reason, jdump(resolved_result), utcnow(), review_id))

    audit("review." + body.action, ctxinfo=ctxinfo, correlation_id=rv["correlation_id"],
          approval_status=approval, reason=body.reason,
          result_summary=f"task={review_id} -> {new_status}")
    updated = row("SELECT * FROM review_tasks WHERE id=?", (review_id,))
    updated["original_result"] = jload(updated["original_result"])
    updated["resolved_result"] = jload(updated["resolved_result"])
    return updated
