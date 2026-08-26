# Sarvam Edge Lab

A local-first demo of an on-device AI product, built end to end: model execution,
hardware compatibility, local/cloud policy, enterprise deployment, observability,
evals, analytics, offline operation, fleet management and rollback.

**This is an interview demo for a Product Manager role at Sarvam.ai. It is NOT
Sarvam Edge production software. Simulated outputs are clearly labelled and are
NOT real Sarvam Edge benchmarks.**

## Product truth (read this first)

| Mode | What runs | How it is labelled |
|---|---|---|
| **Real local mode** | A user-provided Sarvam-1 artifact (for example GGUF) loaded by llama-cpp-python or Transformers | `Real local model` |
| **Demo simulation mode** | A deterministic rules engine. No model needed. Default mode. | `Simulated demo output` |
| **Cloud simulator** | An in-process fake cloud. No real API call happens. | `Cloud simulator` |

- Sarvam-1 is a public base text-completion model, not a chat or ASR/TTS product.
  The demo uses it only if you provide a compatible local artifact.
  The app never downloads unofficial conversions.
- If the real model returns invalid JSON, the system validates the output against
  a typed schema (`TriageResult`), shows the failure, and falls back to the
  deterministic fixture. The fallback reason is always visible.
- The app never claims that simulated results are real Sarvam Edge benchmarks.

## Tech stack

Python 3.11 · FastAPI · Pydantic v2 · SQLite (WAL) · React 18 · TypeScript ·
Vite 5 · Tailwind CSS 3 · pytest · vitest. Charts are hand-rolled SVG (no chart
library). Docker optional; native run needs no containers.

## Setup

**Live demo (Railway):** https://sarvam-edge-lab-production.up.railway.app
One container serves both the API (`/docs`, `/api`-less paths) and the built UI.
SQLite persists on a mounted Railway volume at `/data`. The demo database resets
only if you delete the volume.

Requirements for local run: Python 3.11+ (3.11 preferred), Node 18+, and `uv` (optional but recommended).

```bash
git clone https://github.com/namangoyal3/sarvam-edge-lab.git
cd sarvam-edge-lab
./run.sh            # starts backend :8001 + frontend :5173, seeds demo data
```

`./run.sh --reset` wipes the database first. Stop with Ctrl-C.

### Run the real sub-1GB model and make every number come from it

```bash
bash scripts/local_model.sh          # add --keep-db to preserve existing records
```

This does five things:

1. Loads `~/sarvam-soup/sarvam-1-triage-iq3xxs.gguf` (966 MB) through llama.cpp
   and blocks until `/health` reports `mode=real_local`.
2. Resets the database with the synthetic 7-day backfill **disabled**
   (`SARVAM_SEED_HISTORY=0`), so no generated row can inflate a dashboard.
3. Rolls the artifact to every enrolled device and prints which devices the
   compatibility matrix rejects, with the reason.
4. Replays 30 English / Hindi / Hinglish tickets as real on-device inference.
5. Scores the held-out eval set on the same artifact.

Every figure on Overview, Observability and Evals then comes from that model:
p50 ≈ 1.8 s, 100 % local execution, `current model = ft-iq3xxs`, eval verdict
FAIL at 0.36 task accuracy. Those are measurements, not targets — see
[Model accuracy](#model-accuracy-raising-it-honestly).

Override the artifact with `SARVAM_MODEL_PATH` and `SARVAM_MODEL_ID`.

Manual alternative:

```bash
# backend
cd backend && uv venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --port 8001
# frontend (new terminal)
cd frontend && npm install && npm run dev
```

Docker alternative:

```bash
docker compose up --build     # backend :8001, frontend :5173
```

### Deploying to Railway

The repo root `Dockerfile` builds the React UI and serves it from FastAPI as one
container — one URL, no CORS setup:

```bash
railway init --name sarvam-edge-lab
railway service sarvam-edge-lab     # link (name it whatever you like)
railway up -d                       # build + deploy
railway volume add -m /data         # persistent SQLite (SARVAM_DB_PATH=/data/...)
railway domain                      # generates the public URL
```

Open **http://localhost:5173**. First boot seeds tenants, users, 12 devices,
3 models, 3 policies, a 26-case eval set, cost assumptions and a labelled 7-day
generated history so dashboards are alive immediately.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `SARVAM_MODEL_PATH` | *(empty)* | Path to your local Sarvam-1 artifact (GGUF). Empty = simulation mode. |
| `SARVAM_MODEL_ID` | *(empty)* | Catalog id of that artifact. The Playground selects it by default when a real model is loaded. |
| `SARVAM_SEED_HISTORY` | `1` | `0` skips the generated 7-day backfill so dashboards show real traffic only. |
| `SARVAM_RUNTIME` | `auto` | `auto`, `llama_cpp`, `transformers`, or `fixture`. |
| `SARVAM_DB_PATH` | `backend/data/sarvam_edge.db` | SQLite file location. |
| `DEMO_CONTENT_LOGGING` | `0` | Seed value for content logging. Runtime toggle exists in Observability. |
| `POLICY_FRESHNESS_MINUTES` | `60` | Offline policy age after which high-risk actions lock. |
| `SARVAM_PORT` / `SARVAM_HOST` | `8001` / `127.0.0.1` | Backend bind. |
| `CORS_ORIGINS` | localhost dev origins | Comma-separated allowed origins. |
| `DEMO_API_TOKEN` | *(empty)* | **Set this on public deployments.** Requires `X-Demo-Token` header (or `?token=`) on every route except `/health` and `/docs`. Share the demo as `<url>/?token=<value>`. Empty = open (local dev). |

Optional extra for real local mode:
`backend/.venv/bin/pip install llama-cpp-python` (or `transformers`).

## Tests

```bash
cd backend  && .venv/bin/python -m pytest tests/ -q      # 14 tests
cd frontend && npm test                                   # 10 tests (vitest)
cd frontend && npm run build                              # type-checks too
```

Backend tests cover: schema-valid simulated inference, Hindi detection, policy
rejection of oversize input, local-only policy blocking cloud while offline,
idempotent offline sync without duplicate events, eval reproducibility plus gate
structure, low-confidence → HITL → approve flow, viewer RBAC 403s, compatibility
matrix cases, update/rollback visibility, stale-policy action locking, never-connected
diagnostics, and content-logging defaults.

## Five-minute interview demo

Run `bash scripts/demo.sh` for the scripted version (works headless), or click
through the UI:

1. **Playground → run a local inference.** Note the result fields, confidence,
   validation status, audit event ID and the `Simulated demo output` banner.
2. **Show metadata.** Expand the technical trace: input received → preprocessing
   → model selected → runtime selected → hardware backend selected → inference
   started → validation → policy decision → output returned.
3. **Policies page:** note `Local-only (regulated)` policy. Fleet page: assign it
   to `DEV-1009`.
4. **Top bar: switch Network to Offline.**
5. **Playground: run again on DEV-1009.** It completes locally while offline.
6. **Offline Mode page:** telemetry sits in the bounded queue as `pending_sync`.
7. **Trigger a low-confidence case:** send `[low] my name is Rohit billing issue urgent`
   in the Playground. Status becomes `needs_review` (confidence 0.31).
8. **HITL Review Queue → approve** with a reason. Audit trail updates immutably.
9. **Fleet → reconnect DEV-1002.** Queued cloud-path requests execute automatically.
10. **Offline page → Sync.** Watch idempotent sync (duplicates skipped).
11. **Fleet → DEV-1004 → update… to version 1.5.0.** Rollout recorded.
12. **Same device → rollback.** Version reverts; status `rolled_back`.
13. **Audit Log:** every step above is listed with actor, role, correlation ID.
14. **Evals:** run `simulation engine` then `cloud simulator`; compare accuracy,
    gates, latency deltas. Gates cover category, urgency, language, names,
    amounts and dates — aggregate accuracy alone is never used.

Bonus: set role to `viewer` (top bar) and try any mutation → clean 403.
Disconnect network for >60 min equivalent (set `POLICY_FRESHNESS_MINUTES=0` and
restart) → update/rollback/policy edits return `409 STALE_POLICY`.

## Project structure

```
sarvam-edge-lab/
├── README.md                     this file
├── docker-compose.yml            optional containerised run
├── run.sh                        one-command native run
├── scripts/demo.sh               scripted 14-step API walkthrough
├── backend/
│   ├── requirements.txt          FastAPI, Pydantic, uvicorn, httpx, pytest
│   ├── Dockerfile
│   ├── data/                     SQLite db (created at first boot)
│   ├── app/
│   │   ├── main.py               FastAPI app + lifespan seed
│   │   ├── settings.py           env config + honest runtime-status probe
│   │   ├── db.py                 schema (16 tables), helpers
│   │   ├── schemas.py            typed contracts incl. TriageResult
│   │   ├── seed.py               deterministic fixtures + generated history
│   │   ├── common.py             RBAC ctx, audit + telemetry writers, queue
│   │   ├── pipeline.py           inference orchestration (policy→runtime→HITL)
│   │   ├── engine/
│   │   │   ├── triage.py         deterministic Indic triage rules
│   │   │   ├── runtimes.py       local / fixture / cloud-simulator runtimes
│   │   │   ├── policy.py         pre-inference policy evaluation
│   │   │   └── compat.py         device×model compatibility calculator
│   │   └── routers/              system, inference, devices, catalog,
│   │                             evals, obs (telemetry/analytics/audit), reviews
│   └── tests/test_api.py         14 pytest cases
└── frontend/
    ├── Dockerfile
    └── src/
        ├── App.tsx               layout: sidebar, topbar (network/role/tenant)
        ├── api.ts                fetch client + global refresh bus
        ├── ui.tsx                cards, tables, SVG charts, pills
        └── pages/                Playground, Overview, Fleet, Registry,
                                  Policies, Evals, Observability, OfflineMode,
                                  Reviews, AuditLog
```

## API surface

`POST /inference`, `GET /inference/{id}`, `GET /devices`,
`POST /devices/enroll`, `POST /devices/{id}/heartbeat`, `/offline`, `/reconnect`,
`/update`, `/rollback`, `/policy`, `/disable`, `GET /devices/{id}/diagnostics`,
`GET /models`, `POST /models/register`, `GET /policies`, `POST /policies`,
`GET /evals/datasets`, `POST /evals/run`, `GET /evals/{id}`, `GET /telemetry`,
`POST /telemetry/sync`, `GET /telemetry/queue`, `GET /analytics/summary`,
`GET/POST /analytics/cost-config`, `GET /reviews`, `POST /reviews/{id}/action`,
`GET /audit`, `GET /health`, `POST /system/network`,
`POST /system/content-logging`. Interactive docs at `/docs`.

Demo RBAC uses headers (`X-Demo-Role: admin|reviewer|viewer`,
`X-Tenant-ID`). Data access is tenant-scoped.

## Cost simulation

Editable assumptions (Overview → Unit economics): hardware cost, amortisation
window, local ops per device-month, cloud cost per request, human-handled ticket
cost, update cost per device, monthly volume. Displayed metric is **estimated
cost per successful workflow**, not cost per inference.

## Security and privacy posture (demo-grade)

- No hardcoded secrets; env-based config only.
- Public deployments: set `DEMO_API_TOKEN` (the Railway instance runs behind it).
- Tenant-scoped queries; header-based demo RBAC with server-side checks.
- Input-size limits enforced by policy before inference.
- Typed structured-output validation with safe failure states.
- Raw content logging OFF by default; explicit demo-only toggle with warnings.
- Bounded offline queue (500); append-only audit events; bounded log queries.
- **Not production-certified security.** No encryption at rest, no real authn.

## Model accuracy: raising it honestly

Every runtime below was measured on the same 25-case hand-written eval:

| Runtime | Size | Task acc | Schema | p50 | Notes |
|---|---|---|---|---|---|
| Rules engine | ~20 KB | 1.00 | 1.0 | 51 ms | deterministic labeler; demo default |
| **Classifier head (LinearSVC, char n-grams)** | **~1 MB** | **0.92** | **1.0** | **54 ms** | purpose-built; still beats every LLM variant |
| Sarvam-1 FT v2 IQ2_M | 863 MB | 0.24 | 1.0 | 1.4 s | broken training (see below) |
| Sarvam-1 FT v2 IQ3_XXS | 966 MB | 0.36 | 1.0 | 1.0 s | broken training (see below) |
| Sarvam-1 FT v2 Q4_K_M | 1.4 GB | 0.44 | 1.0 | 1.1 s | breaks the device budget |
| **Sarvam-1 FT v3 IQ3_XXS (served)** | **966 MB** | **0.56** | **1.0** | **1.03 s** | fixed training; short prompt; +20 pts at identical size |
| Sarvam-1 FT v3 IQ3_XXS + q8 embeddings | 1.1 GB | 0.56 | 1.0 | 1.8 s | embedding precision didn't pay at epoch 2 |
| Sarvam-1 FT v3 f16 (reference, never ships) | 4.7 GB | 0.80 | 1.0 | 2.1 s | isolates quantization cost |
| Cloud simulator | — | synthetic | 1.0 | 1.3 s | not a real API |

What the numbers teach:

- Raw generation from the 2-bit quant produced garbage JSON, so decoding runs
  under a GBNF grammar: schema validity is 1.0 by construction, not by luck.
- v1/v2 "fine-tuning" never trained on a single answer token. Every training
  row embedded a 781-token few-shot preamble; the answer started at token ~812
  while max_length was 512 — all 4,294 rows truncated BEFORE the label. The
  model memorised the preamble (hence the billing bias) and never learned the
  task or its stop token. More data made it worse (36→28%) because it was more
  repetitions of a broken lesson — NOT quantization, as this README previously
  claimed.
- v3 fixes it: short prompt/completion rows (~213 tokens), completion-only
  loss, EOS trained. Same 966 MB artifact: 0.36 → 0.56. The f16 reference at
  0.80 now isolates the true quantization cost: 24 points at 3-bit.
- Quantization hurts code-mixed text most: at 3-bit, pure Hindi holds 86%
  while Hinglish collapses to 17% (f16: 86% / 67%).
- A ~1 MB purpose-built head beats every quantized LLM variant 2:1 on this
  task — the argument for task-specific edges over shrunken generalists.
- Critical-field gates (names, amounts, dates) pass everywhere because
  extraction is deterministic. Low-confidence output routes to HITL review.

> "Accuracy is bounded by the artifact. Trust is bounded by the system design.
> Nothing wrong ships silently."

## Known limitations

1. Simulation mode uses a keyword/rules engine, not a neural model. Its quality
   numbers describe the fixture set only.
2. Cloud simulator fabricates latency/cost/confidence uplift from config. No
   network call ever happens.
3. Real local mode requires you to supply a Sarvam-1 artifact and install
   llama-cpp-python yourself; nothing auto-downloads.
4. "Network" is a lab-wide simulated switch, not per-device connectivity.
5. RBAC is header-based demo role-play, not authentication.
6. Eval reproducibility holds for fixture/cloud-sim modes; real-model runs vary.
7. The audit log is append-only within the app; it has no WORM/tamper evidence.
8. Historical dashboard baseline is seeded random-walk data, labelled as such.
9. Single-process SQLite; no concurrency hardening; no migrations framework.
10. Frontend tests are smoke-level; no E2E browser automation included.

## Feature → enterprise product mapping

| Demo capability | What it proves about building an on-device AI product |
|---|---|
| Three labelled runtimes + typed output validation | Model execution is a contract problem: schema-gate everything, degrade safely, label honestly. |
| Compatibility calculator (RAM, OS, chipset arch, runtime) | Hardware fragmentation decides which devices ship which models; warnings vs hard blocks mirror real bring-up. |
| Policy engine evaluated before inference | Enterprise buyers need provable routing guarantees: cloud-prohibited means the data physically never leaves the device. |
| Fleet table + enroll/update/rollback/heartbeat | Deployment is a fleet problem: staged rollouts, version pinning, and rollback are table stakes. |
| Evals with critical-field gates + reproducibility | "Accuracy" alone hides name/amount/date failures that destroy trust in Indic workflows; gated, versioned eval sets catch regressions. |
| Privacy-safe telemetry + content-logging toggle | Observability must be designed privacy-first; raw-content capture is an explicit, auditable exception. |
| Offline queue with backoff + idempotent replay | Edge reality: networks flap. Bounded queues, dedup keys, exponential backoff and drain-on-reconnect keep data loss bounded. |
| Stale-policy lock on high-risk actions | Devices acting on outdated governance is a compliance risk; freshness windows make it visible and enforceable. |
| HITL queue with immutable trail | Low confidence, high risk and invalid outputs need human fallback with audit-grade records. |
| Cost-per-successful-workflow model | On-device economics beat per-request cloud only when you measure end-to-end (hardware amortisation + ops + fallback share). |
| Product metrics panel (activation→first success, repeat usage, escalation rate…) | A PM tracks workflow outcomes and trust signals, not just uptime. |

## Disclaimer

Built as an interview demonstration. Not affiliated with, endorsed by, or
representative of Sarvam.ai's production systems. All "cloud", "fleet" and
"benchmark" behaviours are local simulations.
