"""Deterministic Indic support-triage engine.

This is the rules engine behind simulation mode and the structured-output
fallback. It is NOT a Sarvam model; it exists so the product workflow is
demonstrable with zero artifacts installed.
"""
import hashlib
import re

CATEGORIES = ["billing", "connectivity", "account_access", "performance",
              "data_privacy", "security", "feature_request", "other"]
URGENCIES = ["low", "medium", "high", "critical"]
HIGH_RISK = {"data_privacy", "security"}
LANGS = ["en", "hi", "mixed-hi-en"]

KEYWORDS = {
    "billing": ["bill", "billing", "invoice", "charge", "charged", "payment", "refund",
                "double kat", "kat gaya", "paisa kat",
                "बिल", "भुगतान", "रिफंड", "पैसे कट"],
    "connectivity": ["network", "internet", "wifi", "signal", "disconnect", "not connecting",
                     "kat raha", "band ho gaya", "connect nahi", "इंटरनेट", "नेटवर्क", "सिग्नल", "कनेक्ट"],
    "account_access": ["login", "log in", "password", "otp", "locked out", "signin", "sign in",
                       "blocked my account", "forgot", "खाता", "लॉगिन", "पासवर्ड", "भूल", "लॉक"],
    "performance": ["slow", "hang", "hanging", "crash", "freeze", "freezing", "lag", "laggy",
                    "not responding", "धीमा", "अटक", "टमटम", "latency"],
    "data_privacy": ["delete my data", "data deletion", "privacy", "gdpr", "dpdp",
                     "export my data", "डेटा मिटा", "डिलीट", "निजता", "व्यक्तिगत जानकारी"],
    "security": ["fraud", "unauthorized", "hacked", "suspicious", "otp fraud",
                 "ठगी", "धोखाधड़ी", "हैक"],
    "feature_request": ["feature", "suggest", "would be nice", "add option", "improve",
                        "सुझाव", "नया फीचर", "सुधार"],
}
URGENT_WORDS = ["urgent", "asap", "immediately", "emergency", "critical", "turant",
                "abhi", "jaldi", "kal se", "तुरंत", "जल्दी", "अभी", "foran"]
HINDI_ROMAN = {"nahi", "hai", "kya", "mera", "meri", "kaise", "kar", "karo", "kripya",
               "abhi", "turant", "chahiye", "raha", "rahi", "ho gaya", "dijiye", "de do",
               "kal", "aaj", "band", "kat", "atak", "bhool", "paisa", "paise"}

DEVANAGARI = re.compile(r"[\u0900-\u097F]")
AMOUNT = re.compile(r"(?:₹|rs\.?|inr)\s?([\d,]+(?:\.\d+)?)", re.I)
DATE_PAT = re.compile(r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b|\b(today|tomorrow|kal|aaj)\b", re.I)
NAME_MARKER = re.compile(r"(?:my name is|i am|mera naam|mera nam)", re.I)
NAME_WORDS = r"([A-Z\u0900-\u097F][A-Za-z\u0900-\u097F]*(?:\s+[A-Z\u0900-\u097F][A-Za-z\u0900-\u097F]*){0,2})"


def _hits(text: str) -> dict:
    t = text.lower()
    out = {}
    for cat, kws in KEYWORDS.items():
        n = sum(1 for k in kws if k in t)
        if n:
            out[cat] = n
    return out


def detect_language(text: str) -> str:
    if not text.strip():
        return "en"
    dev = len(DEVANAGARI.findall(text)) / max(len(text), 1)
    if dev > 0.12:
        return "hi"
    words = set(re.findall(r"[a-z']+", text.lower()))
    roman = len(words & HINDI_ROMAN)
    has_dev = DEVANAGARI.search(text) is not None
    if roman >= 2 or (roman >= 1 and has_dev):
        return "mixed-hi-en"
    return "en"


def extract_critical(text: str) -> dict:
    out = {}
    m = AMOUNT.search(text)
    if m:
        val = m.group(1).replace(",", "")
        out["amount"] = f"₹{float(val):g}"
    d = DATE_PAT.search(text)
    if d:
        out["date"] = (d.group(1) or d.group(2)).lower()
    nm = NAME_MARKER.search(text)
    if nm:
        m2 = re.search(NAME_WORDS, text[nm.end():])
        if m2:
            out["person"] = m2.group(1).strip().title()
    return out


def next_action(cat: str, urgency: str) -> str:
    base = {
        "billing": "Open billing review and check the last transaction",
        "connectivity": "Run network diagnostics and refresh the session",
        "account_access": "Trigger identity verification and reset flow",
        "performance": "Collect device logs and restart the app service",
        "data_privacy": "Route to DPA-compliant deletion workflow within 30 days",
        "security": "Freeze suspicious activity and escalate to fraud desk",
        "feature_request": "Log to product backlog for PM triage",
        "other": "Send to general support queue",
    }[cat]
    if urgency in ("high", "critical"):
        base += " — prioritise within 1 hour" + (" and page on-call" if urgency == "critical" else "")
    return base


def classify(text: str, language_hint: str | None = None) -> dict:
    """Returns a TriageResult-shaped dict plus debug signals."""
    hits = _hits(text)
    lang = language_hint if language_hint in LANGS else detect_language(text)
    crit = extract_critical(text)

    if not text.strip():
        return {"category": "other", "urgency": "low", "language": lang,
                "suggested_next_action": next_action("other", "low"),
                "confidence": 0.20,
                "explanation": "Empty input; safe default applied.",
                "_signals": {"hits": {}, "noise": ["empty_input"]}, "_critical": crit}

    noise = []
    conf = 0.58
    top_cat, top_n = ("other", 0)
    ranked = sorted(hits.items(), key=lambda kv: -kv[1])
    if ranked:
        top_cat, top_n = ranked[0]
        conf += 0.09 * min(top_n, 3)
        if len(ranked) > 1 and ranked[1][1] == top_n:
            conf -= 0.08          # ambiguous tie
            noise.append("category_tie")
    else:
        top_cat = "other"
        noise.append("no_keyword_match")

    low_marker = "[low]" in text.lower()
    if low_marker:
        conf = 0.31
        noise.append("forced_low_confidence")
    if len(text.strip()) < 14:
        conf -= 0.22
        noise.append("input_too_short")
    letters = [c for c in text if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.6:
        conf -= 0.10
        noise.append("shouting_caps")

    urgency = "medium"
    if any(w in text.lower() for w in URGENT_WORDS):
        urgency = "high"
    if top_cat == "security":
        urgency = "critical"          # fraud/security incidents page on-call by default
    elif top_cat in HIGH_RISK:
        urgency = "critical" if urgency == "high" else "high"
    if top_cat == "feature_request" and urgency == "medium":
        urgency = "low"
    if AMOUNT.search(text):
        amt = float(AMOUNT.search(text).group(1).replace(",", ""))
        if amt >= 500 and urgency in ("medium", "low"):
            urgency = "high"
    low = text.lower()
    if top_cat == "billing" and any(w in low for w in ("double", "twice", "dobara")):
        urgency = "high"

    conf = max(0.05, min(0.97, round(conf, 2)))
    expl_bits = []
    if ranked:
        expl_bits.append(f"matched {top_n} signal(s) for '{top_cat}'")
    else:
        expl_bits.append("no category signals matched; defaulted to 'other'")
    if noise:
        expl_bits.append("adjustments: " + ", ".join(noise))
    expl_bits.append(f"language detected as {lang}")
    if crit:
        expl_bits.append(f"critical fields: {crit}")

    return {"category": top_cat, "urgency": urgency, "language": lang,
            "suggested_next_action": next_action(top_cat, urgency),
            "confidence": conf,
            "explanation": "; ".join(expl_bits),
            "_signals": {"hits": hits, "noise": noise},
            "_critical": crit}


def jitter(base_ms: int, seed_text: str, spread: float = 0.4) -> int:
    """Deterministic pseudo-latency so demos/evals reproduce exactly."""
    h = int(hashlib.sha256(seed_text.encode()).hexdigest()[:8], 16)
    factor = 1.0 + ((h % 1000) / 1000.0 - 0.5) * 2 * spread
    return max(5, int(base_ms * factor))
