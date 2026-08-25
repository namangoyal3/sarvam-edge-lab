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


def _branch_logprob(llm, toks) -> float:
    lp = 0.0
    for t in toks:
        lp += _logprob_of(_last_logits(llm), int(t))
        llm.eval([int(t)])
    return lp


def _cont_toks(llm, head: str, variant: str):
    """Token sequences of `variant` continuing `head`. Quantized models split
    option words across different BPE paths (e.g. 'b'+'illing' vs 'bi'+'lling');
    returning several plausible segmentations lets _score_field take the max,
    otherwise one strong single-path competitor wins unfairly."""
    hv = llm.tokenize((head + variant).encode("utf-8"), add_bos=False)
    h = llm.tokenize(head.encode("utf-8"), add_bos=False)
    n = 0
    for a, b in zip(h, hv):
        if a != b:
            break
        n += 1
    joint = [int(t) for t in hv[n:]]
    stand = [int(t) for t in llm.tokenize(variant.encode("utf-8"), add_bos=False)]
    out = [joint]
    if stand != joint:
        out.append(stand)
    if len(variant) > 1:
        f = llm.tokenize(variant[0].encode("utf-8"), add_bos=False)
        r = llm.tokenize(variant[1:].encode("utf-8"), add_bos=False)
        split = [int(t) for t in f] + [int(t) for t in r]
        if split not in out:
            out.append(split)
    return out


def _score_field(llm, head: str, options) -> tuple[str, float]:
    # fresh prefill per SEGMENTATION (codex review: alternatives must not start
    # from a context mutated by earlier ones). State restore stays off — Metal
    # corruption verified empirically.
    prefix = llm.tokenize(head.encode("utf-8"), add_bos=True)
    raw = {}
    for opt in options:
        best = -1e9
        for toks in _cont_toks(llm, head, opt):
            llm.reset()
            llm.eval(prefix)
            best = max(best, _branch_logprob(llm, toks))
        raw[opt] = best
    mx = max(raw.values())
    ex = {k: float(np.exp(v - mx)) for k, v in raw.items()}
    z = sum(ex.values())
    probs = {k: v / z for k, v in ex.items()}
    winner = max(probs, key=probs.get)
    return winner, float(probs[winner])


def classify_via_logits(llm, text: str) -> dict | None:
    try:
        from .runtimes import LOCAL_PROMPT
        # strip trailing "JSON:" duplication: the few-shot header already ends
        # with it; appending LOCAL_PROMPT_END produced JSON:\nJSON:
        base = LOCAL_PROMPT.replace("{text}", text[:600])
        cat_head = base + ' {"category": "'
        cat, p_cat = _score_field(llm, cat_head, CATEGORIES)
        urg_head = cat_head + cat + '", "urgency": "'
        urg, p_urg = _score_field(llm, urg_head, URGENCIES)
        lang_head = urg_head + urg + '", "language": "'
        lang, p_lang = _score_field(llm, lang_head, LANGUAGES)
        return {"category": cat, "urgency": urg, "language": lang,
                "confidence": round((p_cat + p_urg + p_lang) / 3.0, 3)}
    except Exception:
        return None
