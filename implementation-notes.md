# Implementation notes

## 2026-08-27 — make every dashboard number come from the local model

Goal: run the fine-tuned sub-1GB Sarvam-1 artifact for real and stop the UI from
reporting anything the model did not produce.

The inference path already worked (`SARVAM_MODEL_PATH` + llama-cpp-python +
GBNF grammar). The dishonesty was upstream of it:

- **420 of 512 telemetry rows were synthetic.** `_seed_history()` writes a
  deterministic 7-day backfill with `model_version=1.4.0` and 40–110 ms
  latencies. Overview reported p50 = 92 ms while the real artifact measures
  ~1 800 ms. Gated behind `SARVAM_SEED_HISTORY`; the local runner sets it to 0.
- **The sub-1GB artifacts were never seeded.** They had been registered at
  runtime via `POST /models/register` in an earlier session, so any `--reset`
  silently deleted them and `model_id=m-sarvam-mini-iq3xxs` 404'd. Moved into
  `seed.MODELS`. Same bug hid `m-ticket-head`, which `pipeline.py` branches on.
- **Eval runs were attributed to the wrong model.** `run_eval` hardcoded
  `m-triage-rules-sim` in the `eval_runs` insert regardless of mode, so a
  local-mode eval showed up on the Evals page as a rules-engine result.
  Now `_eval_model_id(mode)`.
- **`compat.check` called the 1 MB classifier head incompatible** on every
  device, because `kind="classifier"` fell through to the runtime-list check.
  `_local_available` bypasses compat for that kind, so inference worked and only
  the Fleet badge lied. Grouped with `fixture`.
- **The regulated policy (`p-local-only`) did not allow the new artifacts**, so
  switching to it blocked the real model.

`scripts/drive_local.py` rolls the artifact across the fleet, prints which
devices the compatibility matrix rejects and why, then replays 30 en/hi/hinglish
tickets as real inference. Devices are chosen from the roll-out result rather
than hardcoded, so an incompatible device never silently produces a fallback row
that would land in the dashboard as "local".

Measured after the change: 30/30 on-device, 0 fallbacks, p50 1 783 ms,
p95 2 247 ms, 100 % local execution, eval verdict FAIL at 0.36 task accuracy —
consistent with the README matrix. The FAIL is the honest result and stays.

## 2026-08-27 (overnight) — v3 retrain, voice demo, Codex review

- Root cause confirmed by measurement: v1/v2 trained on ZERO answer tokens
  (781-token preamble + answer at ~812 vs max_length 512; 400/400 truncated).
- v3: prompt/completion rows (~213 tok), completion_only_loss, EOS. Same eval:
  f16 0.80; IQ3_XXS e1 0.52 / e2 0.56 (shipped, 966MB, p50 1.03s); q8emb 1.1GB
  no gain at e2. Billing bias gone (22/30 -> 1/30 on live corpus).
- Hinglish is the quantization casualty: hi 86% vs mixed 17% at 3-bit.
- Voice: /inference/voice (whisper.cpp small, threadpooled, 15MB cap). Cold ASR
  ~14s (model load), warm ~0.7s -> demo needs one warm-up call. 4/4 Hindi lines
  classify correctly through garbled TTS transcripts.
- Codex consult (1.28M tokens) found 6 P1s; all fixed or moot. Key ones: demo
  script loaded old artifact; SFT prompt env never exported; drive_local could
  bless fixture traffic (now warm-up asserts "Real local model" + refuses
  fallbacks); SEED_HISTORY=0 now purges generated rows on existing DBs.
- Parallel opencode session committed Railway fixes 01:40-01:59 (seed upsert,
  SQLite busy timeout, classifier label); merged cleanly, verified compatible.
