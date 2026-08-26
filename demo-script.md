# Demo recording — 3 minutes, 5 scenes
QuickTime > File > New Screen Recording. Mic ON. Browser at 110% zoom.
Do Not Disturb ON. Dock hidden. One take per scene; cuts BETWEEN scenes only.
Numbers in [brackets] get filled from the v3 eval before you record.

---

## Scene 1 — Cold open: offline Hindi voice (0:00–0:25)

CLICKS: Menu bar → WiFi OFF (do it slowly, on camera) → browser tab
http://localhost:5173 → press "🎤 Speak ticket" → SPEAK the line below →
press "◼ Stop & triage" → wait for the result card.

SPEAK (into the mic, as the ticket):
  "मेरे खाते से ठगी हुई है, किसी ने बिना पूछे पैसे निकाले हैं, तुरंत जांच करो"
  (fraud complaint -> classifies security/high; verified 4/4 with the v3 model)

SAY (over the result):
  "Everything you just saw — speech recognition and a two-billion-parameter
  Indic language model — ran on this laptop. WiFi is off. The whole model is
  under a gigabyte on disk."

IF the transcript has a wrong word but triage is still billing/high, SAY:
  "Notice it even misheard a word and still triaged it correctly."

---

## Scene 2 — Prove it (0:25–1:00)

CLICKS: Scroll the Result card, then expand "Technical trace".

SAY (pointing with cursor as you go):
  "No screenshots, no mocks — here's the evidence on every request. The
  artifact: a 966-megabyte IQ3 quantized Sarvam-1 fine-tune, served by
  llama.cpp. First trace step: the audio was transcribed on-device and never
  left the machine. Then model selection, runtime, hardware backend, schema
  validation, the policy decision with its reasons, and an audit ID.
  Every request carries its own paper trail."

---

## Scene 3 — Fleet + policy refuses to leak (1:00–1:40)

CLICKS: Sidebar → Device Fleet. Hover the Compat column on 2–3 rejected rows.
Then: on DEV-1002 press "policy…" → pick "Local-only (regulated)".
Back to Playground → set Execution path = "force cloud simulator" → Run
inference → show the blocked/queued result.

SAY:
  "Twelve enrolled devices; the compatibility matrix rejects six of them —
  with reasons: wrong runtime, three gigs of RAM, unsupported OS. That's the
  IT-admin question answered in code.
  Now I've put this device on the regulated local-only policy — the one a
  bank would run. I'll force the cloud path deliberately... and the policy
  engine blocks it before inference, and writes an audit event. The system
  refuses to leak even when asked to."

---

## Scene 4 — A bad release cannot ship (1:40–2:20)

CLICKS: Fleet → DEV-1002 → "update…" → pick "Sarvam-1 triage FT IQ3_XXS
(v2 regression)" if registered, else say the line with the Evals history.
Sidebar → Evals → mode "against: local runtime" → Run eval → point at FAIL.
Fleet → DEV-1002 → "rollback" → point at update_status "rolled_back".
Sidebar → Audit Log → point at the update + rollback entries.

SAY:
  "This is a real bad model — my own v2 fine-tune, which regressed. Watch
  what the platform does with it. The eval gate fails it against explicit
  thresholds — category, urgency, language, critical fields. One click rolls
  the fleet back. And the audit log has who, what, which policy version,
  which model version. A bad model is physically unable to reach this fleet
  quietly."

---

## Scene 5 — The honest close (2:20–3:00)

CLICKS: Evals → Run history (v1 / v2 / v3 rows visible). Then the README
matrix section OR Overview dashboard.

SAY:
  "Same model, same eval, three versions: [0.36], then [0.28] — a regression
  I shipped and caught — and after finding that my training data was being
  truncated before the answer on every single row, [v3 number].
  And the uncomfortable finding: a one-megabyte purpose-built classifier
  scores 0.92 on the same task. So the real product question isn't how
  small the LLM can get — it's which workflows need a general model
  on-device at all. That's what I'd want to work on at Sarvam.
  I'm Naman — happy to go deeper at four."

---

## Pre-flight (I run this for you before you record)
- [x] training finished, GPU free
- [ ] WARM-UP before recording: one throwaway 🎤 voice request (cold ASR is ~14s
      from disk; warm is ~0.7s). Do this off-camera right before Scene 1.
- [x] v3e2 registered + backend serving it (SARVAM_SFT_PROMPT auto-set)
- [x] fresh DB + 30/30 real on-device tickets, p50 1033ms, 0 fallbacks
- [ ] v2 artifact registered so Scene 4's bad-release deploy works
- [x] voice path verified 4/4 categories; other click-paths verified via API
- [x] numbers filled: v1 0.36 / v2 0.28 / v3 0.56 @966MB / f16 0.80 / head 0.92

## Recording hygiene
- Two takes max. Pick the one with better ENERGY, not fewer stumbles.
- If a scene dies, re-record that scene only.
- Upload: Loom or YouTube unlisted. Email line:
  "3-minute demo: <link> — 0:00 offline Hindi voice · 1:40 catching a bad release"
