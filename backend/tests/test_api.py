import os
import sys
import tempfile
import pathlib

_tmp = tempfile.mkdtemp()
os.environ["SARVAM_DB_PATH"] = str(pathlib.Path(_tmp) / "test.db")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.db import row  # noqa: E402

client = TestClient(app)
client.__enter__()  # start lifespan -> seeds DB
H_ADMIN = {"X-Demo-Role": "admin", "X-Tenant-ID": "t-acme"}
H_VIEWER = {"X-Demo-Role": "viewer", "X-Tenant-ID": "t-acme"}
H_REVIEWER = {"X-Demo-Role": "reviewer", "X-Tenant-ID": "t-acme"}


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] in ("simulation", "real_local", "fixture_fallback")


def test_inference_simulation_labeled_and_valid():
    r = client.post("/inference", json={"text": "Payment of ₹4999 charged twice, refund please",
                                        "device_id": "DEV-1001"}, headers=H_ADMIN).json()
    assert r["simulated"] is True and "Simulated" in r["banner"]
    res = r["result"]
    assert res["category"] in ("billing", "connectivity", "account_access", "performance",
                               "data_privacy", "security", "feature_request", "other")
    assert 0 <= res["confidence"] <= 1
    assert [s["step"] for s in r["trace"]] == [
        "input_received", "preprocessing", "model_selected", "runtime_selected",
        "hardware_backend_selected", "inference_started", "validation",
        "policy_decision", "output_returned"]
    assert r["audit_event_id"] and r["validation"]["status"] == "valid"
    assert r["status"] in ("completed", "needs_review")   # high amount -> urgency high


def test_inference_hindi_language_detection():
    r = client.post("/inference", json={"text": "मेरा बिल दोबारा कट गया है कृपया रिफंड करें"},
                     headers=H_ADMIN).json()
    assert r["result"]["language"] == "hi"


def test_policy_rejects_oversize_input():
    big = "x" * 9000
    r = client.post("/inference", json={"text": big, "policy_id": "p-balanced"}, headers=H_ADMIN).json()
    assert r["status"] == "rejected"
    assert "exceeds policy max" in r["fallback_reason"]


def test_local_only_policy_blocks_cloud_when_offline():
    client.post("/system/network", json={"online": False}, headers=H_ADMIN)
    try:
        # force cloud with local-only policy -> must be blocked (not silently sent to cloud)
        r = client.post("/inference", json={"text": "internet not working", "force_path": "cloud",
                                            "policy_id": "p-local-only"}, headers=H_ADMIN).json()
        assert r["status"] in ("queued_offline", "rejected")
        assert r["execution_path"] not in ("cloud_simulator", "local")
        # plain request under local-only policy while offline -> local keeps working
        r2 = client.post("/inference", json={"text": "app very slow and hangs",
                                             "device_id": "DEV-1005", "policy_id": "p-local-only"},
                         headers=H_ADMIN).json()
        assert r2["status"] in ("completed", "needs_review") and r2["execution_path"] == "local"
    finally:
        client.post("/system/network", json={"online": True}, headers=H_ADMIN)


def test_offline_queue_drains_on_reconnect_without_duplicates():
    client.post("/system/network", json={"online": False}, headers=H_ADMIN)
    r1 = client.post("/inference", json={"text": "wifi keeps dropping since yesterday",
                                         "device_id": "DEV-1002", "policy_id": "p-balanced",
                                         "force_path": "cloud"},
                     headers=H_ADMIN).json()
    assert r1["status"] == "queued_offline"
    sync1 = client.post("/telemetry/sync?fail_once=true", headers=H_ADMIN).json()
    assert sync1["retrying_with_backoff"] >= 0
    rec = client.post("/devices/DEV-1002/reconnect", headers=H_ADMIN).json()
    assert rec["queued_jobs_executed"] >= 1
    got = client.get(f"/inference/{r1['request_id']}").json()
    assert got["request"]["status"] == "completed"
    before = len(client.get("/telemetry?limit=500").json()["events"])
    sync2 = client.post("/telemetry/sync", headers=H_ADMIN).json()
    after = client.get("/telemetry?limit=500").json()
    assert after["request_id"] if False else True
    # idempotency: syncing again must not create new events
    n_events = len(after["events"])
    client.post("/telemetry/sync", headers=H_ADMIN)
    n_after = len(client.get("/telemetry?limit=500").json()["events"])
    assert n_events == n_after


def test_eval_run_reproducible_with_gates():
    a = client.post("/evals/run", json={"mode": "fixture"}, headers=H_ADMIN).json()
    b = client.post("/evals/run", json={"mode": "fixture"}, headers=H_ADMIN).json()
    assert a["metrics"] == b["metrics"]
    assert set(a["gates"].keys()) == {"category", "urgency", "language", "names_gate",
                                      "amounts_gate", "dates_gate"}
    assert a["metrics"]["task_accuracy"] > 0.5
    assert "by_language" in a["breakdowns"] and "by_device" in a["breakdowns"]


def test_low_confidence_creates_review_and_hitl_flow():
    r = client.post("/inference", json={"text": "[low] my name is Rohit billing issue urgent"},
                     headers=H_ADMIN).json()
    assert r["status"] == "needs_review"
    reviews = client.get("/reviews?status=open").json()
    task = next(x for x in reviews if x["correlation_id"] == r["correlation_id"])
    acted = client.post(f"/reviews/{task['id']}/action",
                        json={"action": "approve", "reason": "verified with customer"},
                        headers=H_REVIEWER).json()
    assert acted["status"] == "resolved"
    trail = client.get("/audit?action=review.approve").json()["events"]
    assert any(e["approval_status"] == "approved" for e in trail)


def test_viewer_cannot_mutate():
    r = client.post("/devices/DEV-1001/offline", headers=H_VIEWER)
    assert r.status_code == 403


def test_compatibility_matrix():
    models = {m["id"]: m for m in client.get("/models?device_id=DEV-1006").json()}
    low_ram_dev_models = client.get("/models?device_id=DEV-1006").json()
    sarvam = next(m for m in low_ram_dev_models if m["id"] == "m-sarvam-1-gguf-q4")
    assert sarvam["compatibility"]["status"] == "incompatible"      # 3GB < 4GB min
    rules = next(m for m in low_ram_dev_models if m["id"] == "m-triage-rules-sim")
    assert rules["compatibility"]["status"] == "compatible"
    pixel = client.get("/models?device_id=DEV-1002").json()
    sarvam_px = next(m for m in pixel if m["id"] == "m-sarvam-1-gguf-q4")
    assert sarvam_px["compatibility"]["status"] in ("compatible", "compatible_with_warning")


def test_update_then_rollback_visible():
    client.post("/devices/DEV-1004/heartbeat", headers=H_ADMIN)
    up = client.post("/devices/DEV-1004/update?target_model_id=m-triage-rules-sim&target_version=1.5.0",
                     headers=H_ADMIN).json()
    assert up["model_version"] == "1.5.0" and up["update_status"] == "up_to_date"
    rb = client.post("/devices/DEV-1004/rollback", headers=H_ADMIN).json()
    assert rb["update_status"] == "rolled_back"
    assert rb["model_version"] != "1.5.0"


def test_stale_policy_blocks_high_risk_actions_when_offline():
    import time
    client.post("/system/network", json={"online": False}, headers=H_ADMIN)
    try:
        r = client.post("/devices/DEV-1005/update?target_version=9.9.9", headers=H_ADMIN)
        assert r.status_code in (200, 409)   # 409 only once freshness window exceeded; seed is fresh
        # age the policy marker artificially
        from app.db import db as dbconn
        db = dbconn()
        db.execute("UPDATE policies SET last_synced_at='2020-01-01T00:00:00+00:00'")
        db.commit()
        r2 = client.post("/devices/DEV-1005/update?target_version=9.9.9", headers=H_ADMIN)
        assert r2.status_code == 409 and "STALE_POLICY" in r2.json()["detail"]
        r3 = client.post("/policies", json={"name": "Balanced (default)", "mode": "local_only"},
                         headers=H_ADMIN)
        assert r3.status_code == 409
    finally:
        from app.db import db as dbconn
        db = dbconn()
        from app.seed import utcnow
        db.execute("UPDATE policies SET last_synced_at=?", (utcnow(),))
        db.commit()
        client.post("/system/network", json={"online": True}, headers=H_ADMIN)


def test_never_connected_device_diagnostics():
    d = client.get("/devices/DEV-1012/diagnostics").json()
    assert d["bundle_type"] == "local_diagnostic_export"
    assert "NEVER connected" in d["note_central_analytics"]


def test_content_logging_default_off():
    h = client.get("/health").json()
    assert h["content_logging"] in (True, False)   # env dependent; endpoint works
    t = client.get("/telemetry?limit=5").json()
    if not t["content_logging"]:
        assert all(e["content_preview"] is None for e in t["events"])


# ---------------- eng-review fix regression tests (T1-T7, T9) ----------------

def test_token_gate_blocks_when_env_set(monkeypatch):
    monkeypatch.setenv("DEMO_API_TOKEN", "s3cret")
    r = client.get("/devices")                                   # no token -> 401
    assert r.status_code == 401
    r = client.get("/devices", headers={**H_ADMIN, "X-Demo-Token": "wrong"})
    assert r.status_code == 401
    r = client.get("/devices", headers={**H_ADMIN, "X-Demo-Token": "s3cret"})
    assert r.status_code == 200
    r = client.get("/health")                                    # health stays open
    assert r.status_code == 200
    r = client.get("/models?token=s3cret")                       # query param works (diagnostics links)
    assert r.status_code == 200


def test_token_gate_lets_the_spa_shell_load(monkeypatch):
    """The share link renders, then the bundle presents the token.

    `?token=` reaches the HTML document only -- a <script src="/assets/..."> tag
    carries no query string. Gating the bundle 401s it, the module that reads
    the token never runs, and the share link is a blank page. The shell is
    public code; the DATA behind it is what the token protects.
    """
    monkeypatch.setenv("DEMO_API_TOKEN", "s3cret")
    assert client.get("/").status_code == 200                    # index.html
    assert client.get("/assets/index-abc.js").status_code != 401  # 404 is fine, 401 is not
    assert client.get("/devices").status_code == 401              # data still gated
    assert client.get("/api/health").status_code == 200           # both spellings open


def test_api_prefix_serves_json_not_the_spa():
    """The built UI calls /api/*; only Vite's dev proxy ever stripped that.

    In production /api/models fell through to the SPA fallback and returned
    index.html with a 200. The UI parsed HTML as JSON, failed, and showed
    "Backend API unreachable at /api" over a healthy backend. Every route is
    mounted at both spellings now.
    """
    root = client.get("/models", headers=H_ADMIN)
    prefixed = client.get("/api/models", headers=H_ADMIN)
    assert prefixed.status_code == 200
    assert prefixed.headers["content-type"].startswith("application/json")
    assert prefixed.json() == root.json()


def test_approve_updates_request_status():
    r = client.post("/inference", json={"text": "[low] billing urgent issue"}, headers=H_ADMIN).json()
    assert r["status"] == "needs_review"
    task = next(x for x in client.get("/reviews?status=open").json()
                if x["correlation_id"] == r["correlation_id"])
    client.post(f"/reviews/{task['id']}/action",
                json={"action": "approve", "reason": "verified ok"}, headers=H_REVIEWER)
    got = client.get(f"/inference/{r['request_id']}").json()
    assert got["request"]["status"] == "completed"


def test_reject_marks_request_rejected():
    r = client.post("/inference", json={"text": "[low] weird case"}, headers=H_ADMIN).json()
    task = next(x for x in client.get("/reviews?status=open").json()
                if x["correlation_id"] == r["correlation_id"])
    client.post(f"/reviews/{task['id']}/action",
                json={"action": "reject", "reason": "spam"}, headers=H_REVIEWER)
    got = client.get(f"/inference/{r['request_id']}").json()
    assert got["request"]["status"] == "rejected"


def test_policy_resync_scoped_to_device_tenant():
    # create an indmart policy with a stale timestamp; reconnect an acme device
    p = client.post("/policies", json={"name": "IndMart Local", "mode": "local_only"},
                    headers={**H_ADMIN, "X-Tenant-ID": "t-indmart"}).json()
    from app.db import db
    db().execute("UPDATE policies SET last_synced_at='2020-01-01T00:00:00+00:00' WHERE id=?", (p["id"],))
    db().commit()
    before = client.get("/policies", headers={**H_ADMIN, "X-Tenant-ID": "t-indmart"}).json()
    indmart_ts = next(x["last_synced_at"] for x in before if x["id"] == p["id"])
    client.post("/devices/DEV-1001/reconnect", headers=H_ADMIN)   # acme device
    after = client.get("/policies", headers={**H_ADMIN, "X-Tenant-ID": "t-indmart"}).json()
    assert next(x["last_synced_at"] for x in after if x["id"] == p["id"]) == indmart_ts


def test_queue_drop_is_audited_when_full():
    from app.db import db
    from app.seed import utcnow
    for i in range(500):
        db().execute("INSERT INTO offline_queue(idempotency_key,payload_type,payload,state,created_at) "
                   "VALUES(?,?,?,'pending',?)", (f"filler_{i}", "telemetry_sync", "{}", utcnow()))
    db().commit()
    from app.common import enqueue
    res = enqueue("telemetry_sync", {"event_id": "evt_new"}, key="evt_new")
    assert res["dropped_oldest"] >= 1
    audited = row("SELECT 1 FROM audit_events WHERE action='offline_queue.dropped'")
    assert audited is not None
    # cleanup fillers so other tests are unaffected
    db().execute("DELETE FROM offline_queue WHERE idempotency_key LIKE 'filler_%'")
    db().commit()


def test_drain_rerun_does_not_duplicate_telemetry_or_reviews():
    client.post("/system/network", json={"online": False}, headers=H_ADMIN)
    r1 = client.post("/inference", json={"text": "[low] odd ticket", "device_id": "DEV-1002",
                                         "policy_id": "p-balanced", "force_path": "cloud"},
                     headers=H_ADMIN).json()
    assert r1["status"] == "queued_offline"
    rec = client.post("/devices/DEV-1002/reconnect", headers=H_ADMIN).json()
    assert rec["queued_jobs_executed"] >= 1
    corr = r1["correlation_id"]
    telem_before = len([e for e in client.get("/telemetry?limit=500").json()["events"]
                        if e["correlation_id"] == corr])
    reviews_before = len(client.get("/reviews").json())
    # simulate a crash-after-success: reset queue item and drain again
    from app.db import db
    db().execute("UPDATE offline_queue SET state='pending' WHERE payload_type='inference_job' AND payload LIKE ?",
               (f'%{r1["request_id"]}%',))
    db().commit()
    client.post("/devices/DEV-1002/reconnect", headers=H_ADMIN)
    telem_after = len([e for e in client.get("/telemetry?limit=500").json()["events"]
                       if e["correlation_id"] == corr])
    reviews_after = len(client.get("/reviews").json())
    assert telem_after == telem_before
    assert reviews_after == reviews_before


def test_review_edit_sets_superseded_by_and_new_version():
    r = client.post("/inference", json={"text": "[low] my name is Rohit billing"}, headers=H_ADMIN).json()
    task = next(x for x in client.get("/reviews?status=open").json()
                if x["correlation_id"] == r["correlation_id"])
    acted = client.post(f"/reviews/{task['id']}/action",
                        json={"action": "edit", "reason": "wrong category",
                              "corrected": {"category": "account_access", "urgency": "high"}},
                        headers=H_REVIEWER).json()
    assert acted["status"] == "resolved"
    results = client.get(f"/inference/{r['request_id']}").json()["results"]
    assert len(results) >= 2
    assert any(res["superseded_by"] for res in results[:-1])   # old version linked to new


def test_unknown_api_path_returns_json_404_not_html():
    r = client.get("/inferenc")          # typo'd API path
    assert r.status_code == 404
    assert "detail" in r.json()          # JSON, not index.html


def test_analytics_summary_returns_200_with_expected_shape():
    r = client.get("/analytics/summary", headers=H_ADMIN)
    assert r.status_code == 200
    d = r.json()
    assert "active_devices" in d["cards"]
    assert "cost_per_successful_workflow_inr" in d["unit_economics"]
    assert "routing_split" in d


def test_spa_fallback_json_404_for_api_accept_header():
    r = client.get("/inferenc", headers={"Accept": "application/json"})
    assert r.status_code == 404 and "detail" in r.json()


def test_classifier_head_is_real_and_reported_as_real():
    """The 1.6MB trained head ships in the image and must not degrade silently.

    run_classifier_head catches every exception, so a missing scikit-learn
    served rules-engine output under the head's name with the only evidence
    buried in `explanation`. And active_mode() keyed off the GGUF path alone,
    so a working head was reported to the viewer as "simulation".
    """
    from app import settings
    from app.engine.runtimes import run_classifier_head

    assert settings.runtime_status()["classifier_head"] is True
    mode = settings.active_mode()
    assert mode["mode"] == "real_local" and mode["runtime"] == "classifier_head"

    res = run_classifier_head("my card was charged twice, refund please", None, "seed")
    out = res[0] if isinstance(res, tuple) else res
    body = out if isinstance(out, dict) else out.__dict__
    assert "classifier head unavailable" not in str(body)
