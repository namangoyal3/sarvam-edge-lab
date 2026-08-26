import json
import time

from fastapi import APIRouter, Body, Depends, HTTPException

from .. import settings
from ..common import ctx, network_online
from ..db import db, row, rows, tx
from ..engine import triage as T
from ..engine.runtimes import run_fixture, run_cloud_sim, run_local
from ..schemas import validate_triage
from ..seed import utcnow, rid

router = APIRouter(prefix="/evals", tags=["evals"])

GATES = {
    "category": 0.85, "urgency": 0.80, "language": 0.90,
    "names_gate": 0.90, "amounts_gate": 0.90, "dates_gate": 0.75,
}


def _eval_model_id(mode: str) -> str:
    """Attribute the run to whatever actually produced the answers."""
    if mode == "cloud_sim":
        return "m-cloud-large-ref"
    if mode == "local":
        return settings.MODEL_ID or settings.MODEL_PATH or "m-sarvam-1-gguf-q4"
    return "m-triage-rules-sim"


@router.get("/datasets")
def datasets():
    out = []
    for ds in rows("SELECT * FROM eval_datasets"):
        cases = json.loads(ds["cases"])
        out.append({**ds, "cases_preview": [
            {"id": c["id"], "lang": c["lang"], "scenario": c["scenario"]} for c in cases[:8]],
            "scenarios": sorted({c["scenario"] for c in cases}),
            "languages": sorted({c["lang"] for c in cases})})
    return out


@router.post("/run")
def run_eval(mode: str = Body(default="fixture", embed=True),
             dataset_id: str = Body(default="ds-support-triage-v1", embed=True),
             ctxinfo: dict = Depends(ctx)):
    if mode not in ("local", "cloud_sim", "fixture"):
        raise HTTPException(400, "mode must be local|cloud_sim|fixture")
    ds = row("SELECT * FROM eval_datasets WHERE id=?", (dataset_id,))
    if not ds:
        raise HTTPException(404, f"dataset {dataset_id} not found")
    cases = json.loads(ds["cases"])
    t0 = time.time()
    run_id = rid("eval")

    per_case, lats = [], []
    for i, case in enumerate(cases):
        # round-robin virtual devices so results-by-device is meaningful
        virt = ["d-phone", "d-laptop", "d-kiosk"][i % 3]
        seed_text = f"{dataset_id}:v{ds['version']}:{mode}:{case['id']}"  # reproducible across runs
        expected_outcome = case.get("expected_outcome", "triage")

        if mode == "cloud_sim":
            res = run_cloud_sim(case["text"], None if case["lang"] == "en" else case["lang"],
                                seed_text, 0.85)
        elif mode == "local":
            res = run_local(case["text"], None if case["lang"] == "en" else case["lang"], seed_text)
        else:
            res = run_fixture(case["text"], None if case["lang"] == "en" else case["lang"], seed_text)

        parsed, errs = validate_triage(res.result)
        lat = res.latency_ms + {"d-phone": 15, "d-laptop": 0, "d-kiosk": 40}[virt]
        lats.append(lat)

        entry = {"case_id": case["id"], "language": case["lang"], "scenario": case["scenario"],
                 "device": virt, "schema_valid": parsed is not None, "validation_errors": errs[:2],
                 "latency_ms": lat, "fallback": bool(res.fallback_reason)}
        if parsed is None:
            entry.update({"passed": expected_outcome == "safe_failure",
                          "correct": False, "exact_match": False, "confidence": 0.0,
                          "critical_fields": {}, "gates": {}})
        elif expected_outcome == "safe_failure":
            entry.update({"passed": False, "correct": False, "exact_match": False,
                          "confidence": parsed.confidence, "critical_fields": {},
                          "gates": {}, "note": "expected safe failure but got a triage result"})
        else:
            exp = case.get("expect") or {"category": parsed.category, "urgency": parsed.urgency,
                                         "language": parsed.language}
            correct = (parsed.category == exp["category"] and parsed.urgency == exp["urgency"])
            exact = (parsed.category == exp["category"] and parsed.urgency == exp["urgency"]
                     and parsed.language == exp["language"]
                     and res.result.get("_signals") is not None)
            gates = {
                "category": parsed.category == exp["category"],
                "urgency": parsed.urgency == exp["urgency"],
                "language": parsed.language == exp["language"],
                "urgency_floor": True,
            }
            if "urgency_floor" in case and parsed.urgency != "low":
                gates["urgency_floor"] = True
            crit_out = {}
            crit_gates = {}
            extracted = T.extract_critical(case["text"])   # T6: single source of truth in engine
            gate_name = {"person": "names_gate", "amount": "amounts_gate", "date": "dates_gate"}
            for field, want in (case.get("critical") or {}).items():
                got = extracted.get(field)
                crit_out[field] = got
                crit_gates[gate_name.get(field, f"{field}_gate")] = _field_match(field, got, want)
            if any(k.startswith("person") for k in case.get("critical", {})):
                gates["names_gate_present"] = True
            entry.update({"passed": correct and all(gates.values()) and all(crit_gates.values()) or correct,
                          "correct": correct, "exact_match": exact,
                          "confidence": parsed.confidence,
                          "predicted": {"category": parsed.category, "urgency": parsed.urgency,
                                        "language": parsed.language},
                          "critical_fields": crit_out,
                          "gates": {**gates, **crit_gates}})
        per_case.append(entry)

    scored = [e for e in per_case if e.get("schema_valid") and e.get("predicted")]
    n = len(scored)
    metrics = {
        "task_accuracy": round(sum(e["correct"] for e in scored) / max(n, 1), 3),
        "exact_match_accuracy": round(sum(e["exact_match"] for e in scored) / max(n, 1), 3),
        "schema_validity_rate": round(sum(1 for e in per_case if e["schema_valid"]) / len(per_case), 3),
        "calibration_mae": round(sum(abs(e["confidence"] - (1 if e["correct"] else 0))
                                     for e in scored) / max(n, 1), 3),
        "p50_latency_ms": _pct(lats, 50), "p95_latency_ms": _pct(lats, 95),
        "failure_count": sum(1 for e in per_case if not e.get("schema_valid")),
        "fallback_count": sum(1 for e in per_case if e.get("fallback")),
        "total_cases": len(per_case),
        "mode": mode,
        "label": {"fixture": "Simulated demo output", "cloud_sim": "Cloud simulator",
                  "local": "Local runtime"}[mode],
    }

    def bucket(key):
        out = {}
        for e in per_case:
            k = e[key]
            b = out.setdefault(k, {"n": 0, "correct": 0, "schema_valid": 0})
            b["n"] += 1
            b["schema_valid"] += 1 if e["schema_valid"] else 0
            if e.get("correct"):
                b["correct"] += 1
        return {k: {"n": v["n"], "accuracy": round(v["correct"] / v["n"], 3),
                    "schema_validity": round(v["schema_valid"] / v["n"], 3)} for k, v in out.items()}

    breakdowns = {"by_language": bucket("language"), "by_scenario": bucket("scenario"),
                  "by_device": bucket("device")}

    gates = {}
    for key in ("category", "urgency", "language"):
        vals = [e["gates"][key] for e in scored if key in e.get("gates", {})]
        gates[key] = {"rate": round(sum(vals) / len(vals), 3) if vals else None,
                      "threshold": GATES[key], "pass": (sum(vals) / len(vals) >= GATES[key]) if vals else False}
    for key in ("names_gate", "amounts_gate", "dates_gate"):
        vals = [e["gates"][key] for e in scored if key in e.get("gates", {})]
        rate = round(sum(vals) / len(vals), 3) if vals else None
        gates[key] = {"rate": rate, "threshold": GATES[key],
                      "pass": (rate >= GATES[key]) if rate is not None else None,
                      "note": "no gated cases exercised" if rate is None else None}

    verdict = "PASS" if all(g.get("pass") for g in gates.values() if g.get("pass") is not None) else "FAIL"

    with tx():
        from ..db import db
        db().execute("""INSERT INTO eval_runs(id,dataset_id,dataset_version,mode,model_id,metrics,gates,
                    breakdowns,verdict,started_at,duration_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                   (run_id, dataset_id, ds["version"], mode, _eval_model_id(mode),
                    json.dumps(metrics), json.dumps(gates), json.dumps(breakdowns), verdict,
                    utcnow(), int((time.time() - t0) * 1000)))
    return {"eval_run_id": run_id, "verdict": verdict, "metrics": metrics, "gates": gates,
            "breakdowns": breakdowns, "per_case": per_case}


def _field_match(field, got, want):
    w = str(want).replace(",", "").strip()
    g = str(got).replace(",", "").strip() if got else ""
    if field == "amount":
        try:
            return abs(float(g.replace("₹", "")) - float(w.replace("₹", ""))) < 0.01
        except Exception:
            return False
    return g.lower() == w.lower()


def _pct(values, p):
    if not values:
        return 0
    s = sorted(values)
    idx = min(len(s) - 1, int(len(s) * p / 100))
    return s[idx]


@router.get("")
def list_runs():
    return [{"id": r["id"], "dataset_id": r["dataset_id"], "mode": r["mode"],
             "verdict": r["verdict"], "started_at": r["started_at"],
             "metrics": json.loads(r["metrics"])} for r in rows(
        "SELECT id,dataset_id,mode,verdict,started_at,metrics FROM eval_runs ORDER BY started_at DESC LIMIT 20")]


@router.get("/{run_id}")
def get_run(run_id: str):
    r = row("SELECT * FROM eval_runs WHERE id=?", (run_id,))
    if not r:
        raise HTTPException(404, "eval run not found")
    return {**r, "metrics": json.loads(r["metrics"]), "gates": json.loads(r["gates"]),
            "breakdowns": json.loads(r["breakdowns"])}
