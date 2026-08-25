"""Logit-forced classification: instead of free-form JSON generation, each enum
option is scored directly from next-token log-probabilities, giving a heavily
quantised model real confidences instead of a constant 0.00.

Approximation note: each field is scored independently with a cloze prompt
("The <field> of this ticket is <option>") — every option is a full
multi-token continuation scored by exact full-vocabulary softmax at each step,
from an independently re-prefilled prefix, so branches never interact; per
option we try the bare and leading-space tokenisations and keep the higher
log-likelihood, and probabilities are renormalised within that field's closed
option set rather than over the whole vocabulary.
Returned confidence is the MEAN of the three winning renormalised probabilities
(chosen over the product, which over-penalises three-field uncertainty).
"""
import numpy as np

CATEGORIES = ["billing", "connectivity", "account_access", "performance",
              "data_privacy", "security", "feature_request", "other"]
URGENCIES = ["low", "medium", "high", "critical"]
LANGUAGES = ["en", "hi", "mixed-hi-en"]


def _last_logits(llm):
    return np.ctypeslib.as_array(
        llm._ctx.get_logits(), shape=(llm._n_vocab,)).astype(np.float64)


def _logprob_of(logits: np.ndarray, tok: int) -> float:
    m = np.max(logits)
    lse = m + np.log(np.sum(np.exp(logits - m)))
    return float(logits[tok] - lse)


def _branch_logprob(llm, variant: str) -> float:
    toks = llm.tokenize(variant.encode("utf-8"), add_bos=False)
    lp = 0.0
    for t in toks:
        lp += _logprob_of(_last_logits(llm), int(t))
        llm.eval([int(t)])
    return lp


def _score_field(llm, head: str, options) -> tuple[str, float]:
    prefix = llm.tokenize(head.encode("utf-8"), add_bos=True)
    raw = {}
    for opt in options:
        llm.reset()
        llm.eval(prefix)
        raw[opt] = max(_branch_logprob(llm, v) for v in (opt, " " + opt))
    mx = max(raw.values())
    ex = {k: float(np.exp(v - mx)) for k, v in raw.items()}
    z = sum(ex.values())
    probs = {k: v / z for k, v in ex.items()}
    winner = max(probs, key=probs.get)
    return winner, float(probs[winner])


def classify_via_logits(llm, text: str) -> dict | None:
    try:
        t = text[:600]
        cat, p_cat = _score_field(
            llm, f"Support ticket: {t}\nThe category of this ticket is ", CATEGORIES)
        urg, p_urg = _score_field(
            llm, f"Support ticket: {t}\nThe urgency of this ticket is ", URGENCIES)
        lang, p_lang = _score_field(
            llm, f"Support ticket: {t}\nThe language of this ticket is ", LANGUAGES)
        return {"category": cat, "urgency": urg, "language": lang,
                "confidence": round((p_cat + p_urg + p_lang) / 3.0, 3)}
    except Exception:
        return None
