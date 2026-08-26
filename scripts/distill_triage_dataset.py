"""Distill rules-engine labels into an SFT dataset for Sarvam-1 triage.

Generates combinatorial Indic support tickets (en/hi/hinglish, all 8 categories,
urgency modifiers, amounts/names/dates, noise variants) labeled by the demo's
rules engine. Output: alpaca JSONL matching the inference prompt shape.
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.engine.triage import classify  # noqa: E402

rng = random.Random(42)

FIRST = ["Priya Singh", "Rohit Sharma", "Ananya Iyer", "Vikram", "Rahul Verma",
         "Sneha Patel", "Amit Kumar", "Deepak", "Meera Nair", "Arjun Das",
         "Kavita Joshi", "Suresh Babu"]
AMTS = [199, 499, 750, 999, 1200, 1500, 2500, 4999, 5500, 15500]
DATES = ["12/03", "05/09", "21/07", "03/11", "30/01"]

T = {
    "billing": {
        "en": ["My payment of ₹{amt} was charged twice this month, please refund the extra amount.",
               "I was billed ₹{amt} but my plan is only ₹199. Fix this billing error.",
               "Invoice dated {date} shows a wrong charge of ₹{amt} on my card."],
        "hi": ["मेरा बिल दोबारा कट गया है, ₹{amt} वापस करो।",
               "{date} को मेरे खाते से गलत ₹{amt} कटे हैं, कृपया सुधारो।"],
        "mix": ["Sir mera bill double kat gaya hai ₹{amt}, refund chahiye abhi",
                "Payment ₹{amt} dobara kat gaya kal, kripya dekho meri billing issue"],
    },
    "connectivity": {
        "en": ["WiFi keeps disconnecting every few minutes since yesterday.",
               "No internet on my device since morning, network shows connected but nothing loads.",
               "Mobile data keeps dropping whenever I travel between towers."],
        "hi": ["इंटरनेट बार बार बंद हो रहा है, कल से नेटवर्क ही नहीं आ रहा।",
               "मेरा नेटवर्क कट रहा है बार बार, सिग्नल आते ही चला जाता है।"],
        "mix": ["Internet nahi chal raha hai kal se, net band ho gaya hai baar baar",
                "Network kat raha hai continuously, wifi connect nahi ho raha"],
    },
    "account_access": {
        "en": ["I cannot login to my account, password reset email never arrives.",
               "My account got locked after too many OTP attempts, help me sign in.",
               "Forgot my password and the recovery phone number is old."],
        "hi": ["मैं अपने खाते में लॉगिन नहीं कर पा रहा, पासवर्ड भूल गया।",
               "OTP नहीं आ रहा और खाता लॉक हो गया है, कृपया मदद करो।"],
        "mix": ["Account lock ho gaya hai, OTP nahi aa raha hai please help karo",
                "Login nahi ho raha mera, password bhool gaya hu kya karu"],
    },
    "performance": {
        "en": ["The app has become very slow and hangs while loading reports.",
               "Application freezes every time I open the dashboard, it is laggy.",
               "App crashes when I upload large files, performance is terrible."],
        "hi": ["ऐप बहुत धीमा चल रहा है और अटक जाता है।",
               "रिपोर्ट खोलते ही ऐप हैंग हो जाता है, बहुत लैग हो रहा है।"],
        "mix": ["App atak jata hai jab report open karta hu, bahut slow hai",
                "Application hang ho rahi hai baar baar, crash bhi ho jata hai"],
    },
    "data_privacy": {
        "en": ["I want to delete my data and all personal information from your servers.",
               "Please export all my personal data as per the DPDP act request.",
               "Remove my account details from your database for privacy reasons."],
        "hi": ["कृपया मेरा सारा डेटा मिटा दो, यह मेरी निजता का प्रश्न है।",
               "मेरी व्यक्तिगत जानकारी डिलीट करो, DPDP के तहत अनुरोध है।"],
        "mix": ["Mera personal data delete karo please, privacy concern hai",
                "Delete my data from server, DPDP ke hisab se chahiye"],
    },
    "security": {
        "en": ["Someone made unauthorized transactions from my account, possible fraud!",
               "I received a suspicious OTP call asking for my credentials, seems like fraud.",
               "My account was hacked, strange login from another city."],
        "hi": ["मेरे खाते से ठगी हुई है, अनजान लेनदेन हुए हैं।",
               "किसी ने मेरा अकाउंट हैक कर लिया है, शक वाली लॉगिन दिख रही है।"],
        "mix": ["Fraud ho gaya mere account me, unauthorized transaction dekho urgent",
                "Kisi ne hack kiya mera account, suspicious login aa raha hai"],
    },
    "feature_request": {
        "en": ["Suggest adding a dark mode feature in the next update.",
               "Would be nice if you add regional language support option.",
               "Please improve the export reports feature with PDF option."],
        "hi": ["एक नया फीचर सुझाव है - ऐप में डार्क मोड जोड़ो।",
               "सुझाव: हिंदी में और सुधार के लिए वॉइस इनपुट फीचर जोड़ें।"],
        "mix": ["Ek naya feature suggest karta hu, dark mode add karo please",
                "Improve karo notification system, ek option chahiye settings me"],
    },
    "other": {
        "en": ["Hello I need some general information about your services.",
               "What are your customer support working hours?",
               "I have a question about how the loyalty program works."],
        "hi": ["नमस्ते, मुझे आपकी सेवाओं की सामान्य जानकारी चाहिए।",
               "आपका कस्टमर सपोर्ट कब खुला रहता है?"],
        "mix": ["Hello mujhe bas general info chahiye aapki service ke bare me",
                "Customer support kab available hota hai bhai"],
    },
}

URGENT_EN = [" urgent", " asap", " immediately", ""]
URGENT_HI = [" तुरंत", " जल्दी", " अभी", ""]
URGENT_MIX = [" urgent", " turant", " abhi", " jaldi se", ""]
URGENT_MAP = {"en": URGENT_EN, "hi": URGENT_HI, "mix": URGENT_MIX}

NOISE = [
    lambda s: s.upper(),
    lambda s: s + " " + rng.choice(["please help", "kindly resolve", "waiting for reply"]),
    lambda s: s.replace("a", "a"),  # no-op keeps distribution honest
    lambda s: rng.choice(["Hi team, ", "Hello, ", "Dear support, ", ""]) + s,
    lambda s: s + (" My name is " + rng.choice(FIRST) + "."),
]


def make_examples():
    out = []
    for cat, langs in T.items():
        for lang_key, templates in langs.items():
            for tpl in templates:
                for _ in range(80):
                    text = tpl.format(amt=rng.choice(AMTS), date=rng.choice(DATES))
                    if "{amt}" in text or "{date}" in text:
                        text = tpl.format(amt=rng.choice(AMTS), date=rng.choice(DATES))
                    text += rng.choice(URGENT_MAP[lang_key])
                    r = rng.random()
                    if r < 0.35:
                        text = rng.choice(NOISE)(text)
                    hint = {"en": None, "hi": None,
                            "mix": None}[lang_key]  # let engine detect; model must learn too
                    lab = classify(text, hint)
                    if lab["category"] == "other" and cat != "other":
                        continue  # skip label collisions; rules engine must agree
                    conf = lab["confidence"]
                    payload = {
                        "category": lab["category"], "urgency": lab["urgency"],
                        "language": lab["language"],
                        "suggested_next_action": lab["suggested_next_action"],
                        "confidence": round(max(conf, 0.6), 2),
                        "explanation": lab["explanation"].split(";")[0],
                    }
                    out.append({"text": text, "label": json.dumps(payload, ensure_ascii=False)})
    # ambiguous / other-heavy tail so model learns humility
    for _ in range(200):
        text = rng.choice(["thing not working thing issue problem",
                           "hello hello hello?", "aaaaaaaa help",
                           "kuch samajh nahi aa raha kya problem hai",
                           "it just does not work sometimes maybe"])
        lab = classify(text, None)
        payload = {"category": lab["category"], "urgency": lab["urgency"],
                   "language": lab["language"],
                   "suggested_next_action": lab["suggested_next_action"],
                   "confidence": round(lab["confidence"] * 0.8, 2),
                   "explanation": lab["explanation"]}
        out.append({"text": text, "label": json.dumps(payload, ensure_ascii=False)})
    rng.shuffle(out)
    return out


INSTRUCTION = (
    "You are a support-ticket triage engine. Classify the ticket and reply with "
    "ONLY a compact JSON object with keys category (billing|connectivity|"
    "account_access|performance|data_privacy|security|feature_request|other), "
    "urgency (low|medium|high|critical), language (en|hi|mixed-hi-en), "
    "suggested_next_action, confidence, explanation.\n\nTicket: "
)

if __name__ == "__main__":
    data = make_examples()
    rng.shuffle(data)
    n_val = max(60, len(data) // 20)
    # Mirror the runtime prompt byte-for-byte so training == inference distribution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from app.engine.runtimes import LOCAL_PROMPT, LOCAL_PROMPT_END  # noqa: E402

    def to_row(ex):
        return {"text": LOCAL_PROMPT.replace("{text}", ex["text"]) +
                LOCAL_PROMPT_END + " " + ex["label"]}

    out_dir = Path.home() / "sarvam-soup/data"
    with open(out_dir / "triage_train.jsonl", "w") as f:
        for ex in data[n_val:]:
            f.write(json.dumps(to_row(ex), ensure_ascii=False) + "\n")
    with open(out_dir / "triage_val.jsonl", "w") as f:
        for ex in data[:n_val]:
            f.write(json.dumps(to_row(ex), ensure_ascii=False) + "\n")
    print(f"train={len(data)-n_val} val={n_val}")
    from collections import Counter
    cats = Counter(json.loads(ex["label"])["category"] for ex in data)
    print("category spread:", dict(cats))
