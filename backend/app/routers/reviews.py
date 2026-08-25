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
    req_status = {"approve": "completed", "reject": "rejected"}.get(body.action)
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
        with tx() as c:
            req = row("SELECT id FROM inference_requests WHERE id=?", (rv["request_id"],))
            if req:
                old = row("""SELECT id, version FROM inference_results WHERE request_id=?
                          ORDER BY version DESC LIMIT 1""", (rv["request_id"],))
                new_id = rid("res")
                ver = (old["version"] + 1) if old else 1
                if old:   # T7: link superseded version -> reviewer-corrected one
                    c.execute("UPDATE inference_results SET superseded_by=? WHERE id=?",
                              (new_id, old["id"]))
                c.execute("""INSERT INTO inference_results(id,request_id,version,category,urgency,language,
                            suggested_next_action,confidence,explanation,model_version,runtime_version,created_at)
                            SELECT ?,?,?,category,urgency,language,suggested_next_action,
                            ?,?,model_version,runtime_version,? FROM inference_results
                            WHERE id=?""",
                           (new_id, rv["request_id"], ver, corrected["confidence"],
                            corrected["explanation"], utcnow(), old["id"] if old else ""))
                c.execute("UPDATE inference_requests SET status='completed' WHERE id=?", (rv["request_id"],))
    elif body.action == "resolve":
        new_status, resolved_result, approval = "resolved", original, "resolved_no_change"

    with tx() as c:
        c.execute("""UPDATE review_tasks SET status=?, reviewer_id=?, resolution_note=?, resolved_result=?,
                    resolved_at=? WHERE id=?""",
                   (new_status, ctxinfo["user_id"], body.reason, jdump(resolved_result), utcnow(), review_id))
        # T2: keep the source request's status consistent with the human decision
        if req_status and rv.get("request_id"):
            c.execute("UPDATE inference_requests SET status=? WHERE id=?",
                      (req_status, rv["request_id"]))

    audit("review." + body.action, ctxinfo=ctxinfo, correlation_id=rv["correlation_id"],
          approval_status=approval, reason=body.reason,
          result_summary=f"task={review_id} -> {new_status}")
    updated = row("SELECT * FROM review_tasks WHERE id=?", (review_id,))
    updated["original_result"] = jload(updated["original_result"])
    updated["resolved_result"] = jload(updated["resolved_result"])
    return updated
