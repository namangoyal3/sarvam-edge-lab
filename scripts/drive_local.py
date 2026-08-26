#!/usr/bin/env python3
"""Point the fleet at the local Sarvam-1 artifact and fill every dashboard with
traffic that actually executed on it. Stdlib only; run from the repo root."""
import argparse
import json
import statistics
import urllib.error
import urllib.request

# Support tickets in the three languages the product claims to serve.
CORPUS = [
    ("My payment of Rs 4999 was charged twice this month, please refund urgently", "en"),
    ("Card debited but order not confirmed, need the money back", "en"),
    ("Net bar bar disconnect ho raha hai, jaldi fix karo", "mixed-hi-en"),
    ("मेरा इंटरनेट सुबह से नहीं चल रहा है", "hi"),
    ("Cannot login, password reset link never arrives", "en"),
    ("मेरा पासवर्ड भूल गया, लॉगिन नहीं हो रहा", "hi"),
    ("App freezes whenever I open the reports tab", "en"),
    ("App bahut slow ho gaya hai update ke baad", "mixed-hi-en"),
    ("Delete my account and all personal data as per DPDP act", "en"),
    ("मेरे खाते से ठगी हुई है, तुरंत जांच करो", "hi"),
    ("Someone made unauthorized transactions from my account, possible fraud", "en"),
    ("Please add a dark mode option to the app", "en"),
    ("EMI auto-debit fail ho gaya, penalty laga diya", "mixed-hi-en"),
    ("Statement download button returns a 500 error", "en"),
    ("KYC documents upload nahi ho rahe, 3 din se try kar raha hoon", "mixed-hi-en"),
    ("बीमा प्रीमियम का पैसा कट गया लेकिन रसीद नहीं मिली", "hi"),
    ("Wifi drops every evening around 8pm in our branch office", "en"),
    ("Need GST invoice for last quarter, portal shows blank", "en"),
    ("Mera refund 15 din se pending hai, koi update nahi", "mixed-hi-en"),
    ("Two factor authentication SMS not received on my number", "en"),
    ("खाता बंद करना है, प्रक्रिया बताइए", "hi"),
    ("Dashboard numbers do not match the exported CSV", "en"),
    ("Bank statement me galat charge dikh raha hai, dispute karna hai", "mixed-hi-en"),
    ("Suspicious login alert from another city, block my account now", "en"),
]


def call(api, path, method="GET", body=None, tenant="t-acme", role="admin"):
    req = urllib.request.Request(
        api + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Demo-Role": role, "X-Tenant-ID": tenant})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"_error": f"{e.code} {e.read()[:200].decode(errors='replace')}"}


def roll_fleet(api, model_id, version, tenant):
    """Assign the artifact to every device, then report who can actually run it."""
    runnable, blocked = [], []
    for d in call(api, "/devices", tenant=tenant):
        r = call(api, f"/devices/{d['id']}/update?target_model_id={model_id}&target_version={version}",
                 "POST", {}, tenant=tenant)
        if "_error" in r:
            blocked.append((d["id"], r["_error"]))
            continue
        detail = r.get("compatibility_detail", {})
        if detail.get("status") == "incompatible":
            blocked.append((d["id"], "; ".join(detail.get("reasons", []))[:90]))
        else:
            runnable.append(d["id"])
    return runnable, blocked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8001")
    ap.add_argument("--model", default="m-sarvam-mini-iq3xxs")
    args = ap.parse_args()

    model = next((m for m in call(args.api, "/models") if m["id"] == args.model), None)
    if not model:
        raise SystemExit(f"model {args.model} not in the registry")
    version = model["version"]

    # Warm-up: /health saying real_local only proves the file exists and the
    # runtime imports. Prove the GGUF actually loads and answers before
    # touching the fleet -- otherwise every "local" row below is a fixture.
    warm = call(args.api, "/inference", "POST",
                {"text": "warmup: card charged twice, refund", "model_id": args.model})
    if warm.get("label") != "Real local model":
        raise SystemExit(f"artifact did not serve a real result "
                         f"(label={warm.get('label')!r}, fallback={warm.get('fallback_reason')!r})")
    print(f"warmup   : real local inference OK ({warm['latency_ms']}ms)")

    print(f"\nfleet    : rolling {args.model} v{version} to every enrolled device")
    fleet = {}
    for tenant in ("t-acme", "t-indmart"):
        runnable, blocked = roll_fleet(args.api, args.model, version, tenant)
        fleet[tenant] = runnable
        print(f"  {tenant}: {len(runnable)} can run it -> {', '.join(runnable) or 'none'}")
        for did, why in blocked:
            print(f"    skipped {did}: {why}")

    if not fleet["t-acme"]:
        raise SystemExit("no t-acme device can run the artifact; nothing to drive")

    plan = [("t-acme", CORPUS)] + ([("t-indmart", CORPUS[:6])] if fleet["t-indmart"] else [])
    lats, cats, real, fell_back = [], {}, 0, 0
    print(f"\ntraffic  : running real on-device inference ({sum(len(c) for _, c in plan)} tickets)")
    for tenant, corpus in plan:
        devs = fleet[tenant]
        for i, (text, hint) in enumerate(corpus):
            r = call(args.api, "/inference", "POST", {
                "text": text, "language_hint": hint,
                "device_id": devs[i % len(devs)], "model_id": args.model}, tenant=tenant)
            if "_error" in r:
                print(f"  ! {r['_error']}")
                continue
            if r.get("label") == "Real local model":
                real += 1
                lats.append(r["latency_ms"])
                cats[r["result"]["category"]] = cats.get(r["result"]["category"], 0) + 1
            else:
                fell_back += 1
                print(f"  ! fell back: {r.get('fallback_reason') or r.get('status')}")
            print(f"\r  {real} on-device / {fell_back} fallback", end="", flush=True)
    print()
    if lats:
        s = sorted(lats)
        print(f"  latency  p50={s[len(s)//2]}ms  p95={s[int(len(s)*.95)-1]}ms  "
              f"mean={int(statistics.mean(s))}ms  (measured, llama.cpp on this machine)")
        print(f"  categories {cats}")

    print("\neval     : scoring the held-out set on the same artifact")
    ev = call(args.api, "/evals/run", "POST", {"mode": "local", "dataset_id": "ds-support-triage-v1"})
    if "_error" in ev:
        print("  !", ev["_error"])
    else:
        print(f"  verdict={ev.get('verdict')}  " +
              "  ".join(f"{k}={v}" for k, v in (ev.get("summary") or ev.get("metrics") or {}).items()
                        if isinstance(v, (int, float))))

    if real == 0 or fell_back > 0:
        raise SystemExit(f"traffic not fully on-device: {real} real / {fell_back} fallback -- refusing to bless this state")

    c = call(args.api, "/analytics/summary")["cards"]
    print(f"\ndashboard: local={c['local_execution_pct']}%  p50={c['p50_latency_ms']}ms  "
          f"p95={c['p95_latency_ms']}ms  successful={c['successful_workflows']}  "
          f"model={c['current_model_version']}")


if __name__ == "__main__":
    main()
