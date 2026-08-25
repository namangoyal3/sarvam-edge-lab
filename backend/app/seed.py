import json
import random
import uuid
from datetime import datetime, timedelta, timezone

from . import settings
from .db import db, tx, jdump
from .engine import triage as T

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def rid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

# ------------------------------------------------------------------ eval cases
def eval_cases() -> list[dict]:
    return [
        # --- English (scenario tags drive per-scenario breakdowns)
        {"id": "en-1", "lang": "en", "scenario": "clean", "device": "d-phone",
         "text": "My payment of ₹4999 was charged twice this month. Please refund the extra amount.",
         "expect": {"category": "billing", "urgency": "high", "language": "en"}, "critical": {"amount": "₹4999"}},
        {"id": "en-2", "lang": "en", "scenario": "clean", "device": "d-phone",
         "text": "WiFi keeps disconnecting every few minutes since yesterday.",
         "expect": {"category": "connectivity", "urgency": "medium", "language": "en"}},
        {"id": "en-3", "lang": "en", "scenario": "names_numbers", "device": "d-laptop",
         "text": "My name is Rohit Sharma and I cannot login with my password.",
         "expect": {"category": "account_access", "urgency": "medium", "language": "en"}, "critical": {"person": "Rohit Sharma"}},
        {"id": "en-4", "lang": "en", "scenario": "high_risk", "device": "d-phone",
         "text": "I want to delete my data and all personal information from your servers immediately.",
         "expect": {"category": "data_privacy", "urgency": "critical", "language": "en"}},
        {"id": "en-5", "lang": "en", "scenario": "clean", "device": "d-laptop",
         "text": "The app has become very slow and hangs while loading reports.",
         "expect": {"category": "performance", "urgency": "medium", "language": "en"}},
        {"id": "en-6", "lang": "en", "scenario": "feature", "device": "d-tablet",
         "text": "Suggest adding a dark mode feature in the next update.",
         "expect": {"category": "feature_request", "urgency": "low", "language": "en"}},

        # --- Hindi
        {"id": "hi-1", "lang": "hi", "scenario": "clean", "device": "d-phone",
         "text": "मेरा बिल दोबारा कट गया है, कृपया रिफंड करें।",
         "expect": {"category": "billing", "urgency": "medium", "language": "hi"}},
        {"id": "hi-2", "lang": "hi", "scenario": "urgent", "device": "d-phone",
         "text": "इंटरनेट बार बार बंद हो रहा है, यह तुरंत ठीक करो।",
         "expect": {"category": "connectivity", "urgency": "high", "language": "hi"}},
        {"id": "hi-3", "lang": "hi", "scenario": "clean", "device": "d-kiosk",
         "text": "मैं अपने खाते में लॉगिन नहीं कर पा रहा, पासवर्ड भूल गया।",
         "expect": {"category": "account_access", "urgency": "medium", "language": "hi"}},
        {"id": "hi-4", "lang": "hi", "scenario": "high_risk", "device": "d-phone",
         "text": "कृपया मेरा सारा डेटा मिटा दो, यह मेरी निजता का प्रश्न है।",
         "expect": {"category": "data_privacy", "urgency": "high", "language": "hi"}},
        {"id": "hi-5", "lang": "hi", "scenario": "clean", "device": "d-laptop",
         "text": "ऐप बहुत धीमा चल रहा है और अटक जाता है।",
         "expect": {"category": "performance", "urgency": "medium", "language": "hi"}},
        {"id": "hi-6", "lang": "hi", "scenario": "feature", "device": "d-tablet",
         "text": "एक नया फीचर सुझाव है - हिंदी में और सुधार करो।",
         "expect": {"category": "feature_request", "urgency": "low", "language": "hi"}},

        # --- Mixed Hinglish
        {"id": "mix-1", "lang": "mixed-hi-en", "scenario": "clean", "device": "d-phone",
         "text": "Sir mera internet nahi chal raha hai aur bill bhi double kat gaya hai",
         "expect": {"category": "billing", "urgency": "high", "language": "mixed-hi-en"}},
        {"id": "mix-2", "lang": "mixed-hi-en", "scenario": "names_numbers", "device": "d-phone",
         "text": "Mera naam Priya Singh hai, payment ₹1200 abhi tak refund nahi hua hai kripya dekho",
         "expect": {"category": "billing", "urgency": "high", "language": "mixed-hi-en"},
         "critical": {"person": "Priya Singh", "amount": "₹1200"}},
        {"id": "mix-3", "lang": "mixed-hi-en", "scenario": "clean", "device": "d-tablet",
         "text": "App atak jata hai jab main report open karta hu, bahut slow hai",
         "expect": {"category": "performance", "urgency": "medium", "language": "mixed-hi-en"}},
        {"id": "mix-4", "lang": "mixed-hi-en", "scenario": "urgent", "device": "d-phone",
         "text": "Account lock ho gaya hai, OTP nahi aa raha, turant help karo please",
         "expect": {"category": "account_access", "urgency": "high", "language": "mixed-hi-en"}},

        # --- Noisy / ambiguous
        {"id": "noisy-1", "lang": "en", "scenario": "noisy", "device": "d-phone",
         "text": "BILL BILL BILL CHARGED WRONG WRONG WRONG",
         "expect": {"category": "billing", "urgency": "medium", "language": "en"}},
        {"id": "noisy-2", "lang": "en", "scenario": "ambiguous", "device": "d-laptop",
         "text": "thing not working thing issue problem thing",
         "expect_any_category": True, "urgency_floor": "low"},
        {"id": "noisy-3", "lang": "mixed-hi-en", "scenario": "noisy", "device": "d-kiosk",
         "text": "net band ho gaya hai kal se aaj bhi nahi chal raha",
         "expect": {"category": "connectivity", "urgency": "high", "language": "mixed-hi-en"}},

        # --- Names & numbers gates
        {"id": "nn-1", "lang": "en", "scenario": "names_numbers", "device": "d-laptop",
         "text": "My name is Ananya Iyer, invoice dated 12/03 shows ₹15,500 charged but plan is ₹999",
         "expect": {"category": "billing", "urgency": "high", "language": "en"},
         "critical": {"person": "Ananya Iyer", "amount": "₹15500", "date": "12/03"}},
        {"id": "nn-2", "lang": "mixed-hi-en", "scenario": "names_numbers", "device": "d-phone",
         "text": "Mera naam Vikram hai aur 05/09 ko ₹750 extra charge hua hai",
         "expect": {"category": "billing", "urgency": "high", "language": "mixed-hi-en"},
         "critical": {"person": "Vikram", "amount": "₹750", "date": "05/09"}},
        {"id": "nn-3", "lang": "en", "scenario": "names_numbers", "device": "d-tablet",
         "text": "This is Rahul Verma, my OTP fraud attempt happened today on my account",
         "expect": {"category": "security", "urgency": "critical", "language": "en"},
         "critical": {"date": "today"}},

        # --- High risk
        {"id": "hr-1", "lang": "en", "scenario": "high_risk", "device": "d-phone",
         "text": "Someone made unauthorized transactions from my account, possible fraud, urgent!",
         "expect": {"category": "security", "urgency": "critical", "language": "en"}},
        {"id": "hr-2", "lang": "hi", "scenario": "high_risk", "device": "d-kiosk",
         "text": "मेरे खाते से ठगी हुई है, तुरंत जांच करो।",
         "expect": {"category": "security", "urgency": "critical", "language": "hi"}},
        {"id": "hr-3", "lang": "en", "scenario": "high_risk", "device": "d-laptop",
         "text": "Requesting full export and deletion of my personal data as per DPDP act",
         "expect": {"category": "data_privacy", "urgency": "high", "language": "en"}},

        # --- Malformed / must end in safe failure
        {"id": "mal-1", "lang": "en", "scenario": "malformed", "device": "d-phone",
         "text": "", "expected_outcome": "safe_failure"},
        {"id": "mal-2", "lang": "en", "scenario": "oversize", "device": "d-phone",
         "text": "x" * 9000, "expected_outcome": "safe_failure"},
    ]


# ------------------------------------------------------------------ seed
DEVICES = [
    ("DEV-1001", "t-acme", "Field Agent Phone A", "Android 14", 4, "Octa-core 2.0GHz", "none", "Helio G85", "llama-cpp-python"),
    ("DEV-1002", "t-acme", "Supervisor Pixel", "Android 14", 8, "Tensor G3", "Immortalis-G715 NPU", "Tensor G3", "llama-cpp-python"),
    ("DEV-1003", "t-acme", "iOS Field Device", "iOS 17", 4, "A15 Bionic", "Apple GPU 4-core", "A15 Bionic", "coreml"),
    ("DEV-1004", "t-acme", "Support Desk Laptop", "Windows 11", 16, "Core i5-1135G7", "Iris Xe", "Core i5-1135G7", "onnx-runtime"),
    ("DEV-1005", "t-acme", "Manager MacBook", "macOS 14", 8, "Apple M1", "Apple GPU 7-core", "M1", "llama-cpp-python"),
    ("DEV-1006", "t-indmart", "Store Kiosk Low-RAM", "Android 12", 3, "Quad-core 1.8GHz", "none", "Exynos 1330", "tflite"),
    ("DEV-1007", "t-indmart", "Warehouse Tablet", "iPadOS 17", 8, "Apple M1", "Apple GPU 8-core", "M1", "coreml"),
    ("DEV-1008", "t-indmart", "Legacy Windows Terminal", "Windows 10", 8, "Core i7-8550U", "UHD 620", "Core i7-8550U", "onnx-runtime"),
    ("DEV-1009", "t-acme", "Rural Tablet (offline-prone)", "Android 13", 6, "Snapdragon 695", "Adreno 619", "Snapdragon 695", "llama-cpp-python"),
    ("DEV-1010", "t-indmart", "Edge Gateway Jetson", "Linux Yocto", 8, "Jetson Orin Nano", "1024-core GPU", "Jetson Orin Nano", "onnx-runtime"),
    ("DEV-1011", "t-indmart", "Retail Android B", "Android 14", 6, "Dimensity 7020", "none", "rk3588", "llama-cpp-python"),
    ("DEV-1012", "t-acme", "Factory-Floor Gateway (never connected)", "Linux Debian 12", 4, "RK3588", "Mali-G610", "rk3588", "llama-cpp-python"),
]

MODELS = [
    dict(id="m-triage-rules-sim", name="Support Triage Rules Engine (Simulated)", task="support-ticket-triage",
         param_count="n/a (rule-based)", artifact_size_mb=0.02, precision="int-exact", quantization="none",
         runtime="embedded-python", supported_os=["any"], supported_chipsets=["any"], supported_runtimes=["embedded-python"],
         min_ram_gb=0.5, recommended_ram_gb=1, expected_latency_ms=60, version="1.4.0",
         release_status="demo_fixture", checksum=None, signature="self-demo-signed", kind="fixture"),
    dict(id="m-sarvam-1-gguf-q4", name="Sarvam-1 GGUF Q4_K_M (user-provided artifact)", task="text-generation (triage via prompted JSON)",
         param_count="~2B (per public card)", artifact_size_mb=1310, precision="int4", quantization="Q4_K_M",
         runtime="llama.cpp family", supported_os=["linux", "macos", "windows", "android"], supported_chipsets=["m1", "m2", "core i5-1135g7", "ryzen 5 5500u", "tensor g3"],
         supported_runtimes=["llama-cpp-python"], min_ram_gb=4, recommended_ram_gb=6, expected_latency_ms=450,
         version="user-artifact", release_status="external_artifact_required",
         checksum=None, signature="unsigned-user-provided", kind="local"),
    dict(id="m-cloud-large-ref", name="Sarvam Large (cloud simulator reference)", task="support-ticket-triage",
         param_count="undisclosed", artifact_size_mb=None, precision="bf16", quantization="server-side",
         runtime="cloud", supported_os=["any"], supported_chipsets=[], supported_runtimes=["cloud"],
         min_ram_gb=0, recommended_ram_gb=0, expected_latency_ms=1200, version="sim-v3",
         release_status="simulator_reference_only", checksum=None, signature="n/a", kind="cloud_ref"),
]

POLICIES = [
    dict(id="p-balanced", name="Balanced (default)", mode="local_preferred", offline_queue_enabled=1,
         max_input_bytes=4000, allowed_data_classes=["support_text"], allowed_models=[],
         allowed_device_ids=[], min_confidence=0.55, hitl_risk_threshold="high"),
    dict(id="p-local-only", name="Local-only (regulated)", mode="local_only", offline_queue_enabled=1,
         max_input_bytes=2000, allowed_data_classes=["support_text"], allowed_models=["m-triage-rules-sim", "m-sarvam-1-gguf-q4"],
         allowed_device_ids=[], min_confidence=0.50, hitl_risk_threshold="medium"),
    dict(id="p-cloud-ok", name="Cloud-allowed (non-sensitive tenant)", mode="cloud_allowed", offline_queue_enabled=0,
         max_input_bytes=8000, allowed_data_classes=["support_text", "public_feedback"], allowed_models=[],
         allowed_device_ids=[], min_confidence=0.55, hitl_risk_threshold="high"),
]


def run_seed(force: bool = False):
    if db().execute("SELECT COUNT(*) c FROM tenants").fetchone()["c"] and not force:
        return
    now = utcnow()
    with tx() as c:
        c.execute("INSERT INTO tenants VALUES('t-acme','Acme Bank Support',?)", (now,))
        c.execute("INSERT INTO tenants VALUES('t-indmart','IndMart Retail Ops',?)", (now,))
        users = [
            ("u-naman", "t-acme", "Naman (Demo Admin)", "admin", 60, 90),
            ("u-rev1", "t-acme", "Reviewer One", "reviewer", 240, None),
            ("u-view1", "t-acme", "Viewer One", "viewer", 300, None),
            ("u-indmgr", "t-indmart", "IndMart Ops Manager", "admin", 120, 180),
        ]
        for uid, tid, name, role, act_min, succ_min in users:
            act = (datetime.now(timezone.utc) - timedelta(minutes=act_min)).isoformat(timespec="seconds")
            succ = ((datetime.now(timezone.utc) - timedelta(minutes=succ_min)).isoformat(timespec="seconds")) if succ_min else None
            c.execute("INSERT INTO users VALUES(?,?,?,?,?,?)", (uid, tid, name, role, act, succ))

        c.executemany(
            "INSERT INTO runtimes VALUES(?,?,?,?,?,?)",
            [("rt-llama-cpp", "llama-cpp-python", "0.2.90", "CPU (AVX2/NEON), Metal, CUDA", jdump(["linux", "macos", "windows"]), "primary local runtime for GGUF artifacts"),
             ("rt-onnx", "onnx-runtime", "1.18", "CPU, DirectML, CoreML", jdump(["linux", "macos", "windows"]), "used on Windows laptops"),
             ("rt-coreml", "coreml-tools runtime", "4.0", "ANE/GPU", jdump(["macos", "ios"]), "Apple devices"),
             ("rt-tflite", "tensorflow-lite", "2.16", "NNAPI/GPU delegate", jdump(["android"]), "low-end Android"),
             ("rt-cloudsim", "cloud-simulator", "1.1", "in-process", jdump(["any"]), "NOT a real cloud API")])

        for d in DEVICES:
            did, tid, name, os_, ram, cpu, gpu, chipset, rt = d
            nc = 1 if did == "DEV-1012" else 0
            status = "offline" if did == "DEV-1009" else "online"
            hb = None if nc else now
            batt = 42 if did == "DEV-1009" else 80
            thermal = "elevated" if did == "DEV-1010" else "nominal"
            c.execute("""INSERT INTO devices(id,tenant_id,name,os,ram_gb,cpu,gpu_npu,chipset,runtime,
                        model_id,model_version,policy_id,status,battery_pct,thermal,last_heartbeat,
                        compatibility,update_status,never_connected,enrolled_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (did, tid, name, os_, ram, cpu, gpu, chipset, rt,
                       "m-triage-rules-sim", "1.4.0", "p-balanced", status, batt, thermal, hb,
                       "unknown", "up_to_date", nc, now))

        for m in MODELS:
            c.execute("""INSERT INTO models(id,name,task,param_count,artifact_size_mb,precision,quantization,
                        runtime,supported_os,supported_chipsets,supported_runtimes,min_ram_gb,recommended_ram_gb,
                        expected_latency_ms,version,release_status,checksum,signature,kind,registered_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (m["id"], m["name"], m["task"], m["param_count"], m["artifact_size_mb"], m["precision"],
                       m["quantization"], m["runtime"], jdump(m["supported_os"]), jdump(m["supported_chipsets"]),
                       jdump(m["supported_runtimes"]), m["min_ram_gb"], m.get("recommended_ram_gb"),
                       m["expected_latency_ms"], m["version"], m["release_status"], m["checksum"],
                       m["signature"], m["kind"], now))

        for p in POLICIES:
            c.execute("""INSERT INTO policies(id,tenant_id,name,mode,offline_queue_enabled,max_input_bytes,
                        allowed_data_classes,allowed_models,allowed_device_ids,min_confidence,hitl_risk_threshold,
                        version,last_synced_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (p["id"], "t-acme", p["name"], p["mode"], p["offline_queue_enabled"], p["max_input_bytes"],
                       jdump(p["allowed_data_classes"]), jdump(p["allowed_models"]), jdump(p["allowed_device_ids"]),
                       p["min_confidence"], p["hitl_risk_threshold"], 1, now, now))

        ds_id = "ds-support-triage-v1"
        cases = eval_cases()
        c.execute("INSERT INTO eval_datasets VALUES(?,?,?,?,?,?)",
                  (ds_id, "Indic Support Triage Eval Set", 1, jdump(cases), len(cases), now))

        cost = [("hardware_cost_per_device_inr", "Device hardware cost", 18000, "INR one-time"),
                ("amortize_months", "Hardware amortisation window", 24, "months"),
                ("local_ops_cost_device_month_inr", "Local ops cost per device/month", 40, "INR/month"),
                ("cloud_cost_per_request_inr", "Cloud cost per request", 0.85, "INR/request"),
                ("human_support_cost_per_ticket_inr", "Human-handled ticket cost", 45, "INR/ticket"),
                ("model_update_cost_per_device_inr", "Model update cost per device", 0.20, "INR/update"),
                ("monthly_request_volume", "Monthly request volume", 50000, "requests/month")]
        for k, label, v, unit in cost:
            c.execute("INSERT INTO cost_config VALUES(?,?,?,?)", (k, label, v, unit))

        _seed_history(c)
        db().commit()


def _seed_history(c):
    """Deterministic 7-day generated history so dashboards are alive on first boot."""
    rng = random.Random(42)
    base = datetime.now(timezone.utc) - timedelta(days=7)
    texts = [
        "Payment charged twice please refund", "Internet nahi chal raha hai",
        "Cannot login password forgot", "App is very slow and freezes",
        "Delete my data as per DPDP", "Suspicious transaction urgent",
        "Suggest dark mode feature", "WiFi disconnects daily",
    ]
    events = []
    reqs = []
    for i in range(420):
        ts = (base + timedelta(minutes=i * 24 + rng.randint(0, 20))).isoformat(timespec="seconds")
        dev = rng.choice(DEVICES[:11])
        path = rng.choices(["local", "cloud_simulator", "queued_offline"], weights=[72, 20, 8])[0]
        ok = rng.random() > 0.04
        lat = rng.randint(38, 110) if path == "local" else rng.randint(850, 1700) if path == "cloud_simulator" else 0
        eid = f"evt_gen_{i:05d}"
        corr = f"corr_gen_{i:05d}"
        err = None if ok else rng.choice(["E_VALIDATION", "E_TIMEOUT", "E_RUNTIME_CRASH"])
        fb = None if path != "cloud_simulator" or rng.random() > 0.25 else "local_runtime_unavailable"
        conf = round(rng.uniform(0.55, 0.95) if ok else rng.uniform(0.2, 0.5), 2)
        events.append((eid, ts, dev[1], dev[0], corr, "1.4.0", "0.2.90", 1, path, lat,
                       1 if ok else 0, err, fb, conf, rng.randint(40, 900), rng.randint(120, 400),
                       "synced" if path != "queued_offline" else "drained", 1, None, 1))
        if ok:
            reqs.append((f"req_gen_{i:05d}", corr, dev[1], dev[0], "u-naman", "p-balanced",
                         "m-triage-rules-sim", rng.randint(40, 600), "completed", path, fb, lat,
                         0.85 if path == "local" else 0.85, ts))
    c.executemany("""INSERT INTO telemetry_events(event_id,ts,tenant_id,device_id,correlation_id,model_version,
                    runtime_version,policy_version,execution_path,latency_ms,success,error_code,fallback_reason,
                    confidence,input_bytes,output_bytes,queue_state,synced,content_preview,is_generated)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", events)
    c.executemany("""INSERT INTO inference_requests(id,correlation_id,tenant_id,device_id,user_id,policy_id,
                    model_id,input_bytes,status,execution_path,fallback_reason,latency_ms,estimated_cost_inr,requested_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", reqs)
