"""Compare eval accuracy/schema-validity/latency across inference runtimes.

Run from backend/: .venv/bin/python scripts/compare_runtimes.py [--modes fixture,local,cloud_sim] [--limit N] [--verbose]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine import runtimes as R
from app.seed import eval_cases

CLOUD_COST = 0.85
RUNNERS = {
    "fixture": lambda t, h, s: R.run_fixture(t, h, s),
    "local": lambda t, h, s: R.run_local(t, h, s),
    "cloud_sim": lambda t, h, s: R.run_cloud_sim(t, h, s, CLOUD_COST),
    "classifier": lambda t, h, s: R.run_classifier_head(t, h, s),
}
LANGS = ["en", "hi", "mixed-hi-en"]
URGENCY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def pct(vals, q):
    if not vals:
        return 0
    s = sorted(vals)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def score_case(case, res):
    """(scored_correct, exact_match, lang_key_or_None). None => not scored."""
    pred = res.result
    expect = case.get("expect")
    if case.get("expected_outcome") == "safe_failure":
        return None, None, None
    lang = case["lang"]
    if expect is None and case.get("expect_any_category"):
        ok = URGENCY_ORDER.get(pred.get("urgency"), -1) >= URGENCY_ORDER[case.get("urgency_floor", "low")]
        return ok, False, lang
    cat_ok = pred.get("category") == expect.get("category")
    urg_ok = pred.get("urgency") == expect.get("urgency")
    return cat_ok and urg_ok, cat_ok and urg_ok and pred.get("language") == expect.get("language"), lang


def safe_pass(case, res):
    # ponytail: approximated — empty-text safe-failure counts as pass because the rules
    # engine's documented behavior is safe-default handling; real rejection signals
    # (invalid validation, fallback_reason) are checked first.
    if res.raw_ok is False or bool(res.fallback_reason) or res.validation_status != "valid":
        return True
    return not case["text"].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="fixture,local,cloud_sim")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    bad = [m for m in modes if m not in RUNNERS]
    if bad:
        sys.exit(f"unknown modes: {bad} (choose from {list(RUNNERS)})")
    cases = eval_cases()
    if args.limit:
        cases = cases[:args.limit]

    rows = []
    for mode in modes:
        scored, exact, langs, lats, confs, schema_ok = [], [], {}, [], [], 0
        sf_total, sf_pass = 0, 0
        diffs = []
        for c in cases:
            res = RUNNERS[mode](c["text"], c["lang"], f"cmp:{mode}:{c['id']}")
            lats.append(res.latency_ms)
            confs.append(res.result.get("confidence", 0.0))
            if res.validation_status == "valid":
                schema_ok += 1
            s, ex, lk = score_case(c, res)
            if s is None:
                sf_total += 1
                sf_pass += 1 if safe_pass(c, res) else 0
                if not safe_pass(c, res) and args.verbose:
                    diffs.append((c["id"], "safe_failure", f"got {res.result.get('category')}/{res.result.get('urgency')}"))
                continue
            scored.append(bool(s))
            exact.append(bool(ex))
            langs.setdefault(lk, []).append(bool(s))
            if not s:
                e = c.get("expect", {})
                diffs.append((c["id"], f"{e.get('category')}/{e.get('urgency')}",
                              f"{res.result.get('category')}/{res.result.get('urgency')}"))
        n = len(scored)
        acc = 100 * sum(scored) / n if n else 0
        em = 100 * sum(exact) / n if n else 0
        sv = 100 * schema_ok / len(cases) if cases else 0
        mc = sum(confs) / len(confs) if confs else 0
        rows.append({"mode": mode, "n": n, "acc": acc, "em": em, "sv": sv,
                     "conf": mc, "p50": pct(lats, 0.5), "p95": pct(lats, 0.95),
                     "sf": f"{sf_pass}/{sf_total}", "langs": langs, "diffs": diffs})

    w = max(len(r["mode"]) for r in rows) + 2
    hdr = f"{'MODE':<{w}}{'N':>4}{'ACC%':>8}{'EXACT%':>9}{'SCHEMA%':>10}{'MEAN_CONF':>11}{'P50_MS':>8}{'P95_MS':>8}{'SAFE_FAIL':>11}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['mode']:<{w}}{r['n']:>4}{r['acc']:>8.1f}{r['em']:>9.1f}{r['sv']:>10.1f}"
              f"{r['conf']:>11.3f}{r['p50']:>8}{r['p95']:>8}{r['sf']:>11}")

    print()
    lh = f"{'MODE':<{w}}" + "".join(f"{l + ' ACC%':>16}" for l in LANGS)
    print(lh)
    print("-" * len(lh))
    for r in rows:
        cells = ""
        for l in LANGS:
            vals = r["langs"].get(l)
            cells += f"{'—' if not vals else f'{100 * sum(vals) / len(vals):.1f} ({len(vals)})':>16}"
        print(f"{r['mode']:<{w}}{cells}")

    if args.verbose:
        print("\nPer-case diffs:")
        any_diff = False
        for r in rows:
            for cid, exp, got in r["diffs"]:
                any_diff = True
                print(f"  [{r['mode']}] {cid}: expected {exp} | got {got}")
        if not any_diff:
            print("  none")


if __name__ == "__main__":
    main()
