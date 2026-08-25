import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import settings

DDL = """
CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','reviewer','viewer')),
  activated_at TEXT, first_success_at TEXT
);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL,
  os TEXT NOT NULL, ram_gb REAL NOT NULL, cpu TEXT NOT NULL,
  gpu_npu TEXT NOT NULL DEFAULT 'none', chipset TEXT NOT NULL,
  runtime TEXT NOT NULL, runtime_version TEXT NOT NULL DEFAULT '1.0.0',
  model_id TEXT, model_version TEXT, policy_id TEXT,
  status TEXT NOT NULL DEFAULT 'online' CHECK(status IN ('online','offline','disabled')),
  battery_pct INTEGER DEFAULT 80, thermal TEXT DEFAULT 'nominal',
  last_heartbeat TEXT, compatibility TEXT DEFAULT 'unknown',
  update_status TEXT DEFAULT 'up_to_date', never_connected INTEGER DEFAULT 0,
  enrolled_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS models (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, task TEXT NOT NULL,
  param_count TEXT, artifact_size_mb REAL, precision TEXT, quantization TEXT,
  runtime TEXT NOT NULL, supported_os TEXT NOT NULL,        -- json list
  supported_chipsets TEXT NOT NULL,                          -- json list
  supported_runtimes TEXT NOT NULL,                          -- json list
  min_ram_gb REAL NOT NULL, recommended_ram_gb REAL,
  expected_latency_ms INTEGER, version TEXT NOT NULL,
  release_status TEXT NOT NULL, checksum TEXT, signature TEXT DEFAULT 'unsigned',
  kind TEXT NOT NULL DEFAULT 'local',                        -- local | fixture | cloud_ref
  registered_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runtimes (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
  backend TEXT NOT NULL, supported_os TEXT NOT NULL, notes TEXT
);
CREATE TABLE IF NOT EXISTS policies (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL,
  mode TEXT NOT NULL CHECK(mode IN ('local_only','local_preferred','cloud_allowed','cloud_disabled')),
  offline_queue_enabled INTEGER NOT NULL DEFAULT 1,
  max_input_bytes INTEGER NOT NULL,
  allowed_data_classes TEXT NOT NULL,     -- json list
  allowed_models TEXT NOT NULL,           -- json list, empty = all
  allowed_device_ids TEXT NOT NULL,       -- json list, empty = all
  min_confidence REAL NOT NULL,
  hitl_risk_threshold TEXT NOT NULL,      -- medium | high | critical
  version INTEGER NOT NULL DEFAULT 1,
  last_synced_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inference_requests (
  id TEXT PRIMARY KEY, correlation_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
  device_id TEXT, user_id TEXT, policy_id TEXT, model_id TEXT,
  input_bytes INTEGER NOT NULL, language_hint TEXT,
  status TEXT NOT NULL,                    -- completed | queued_offline | rejected | needs_review | failed
  execution_path TEXT, fallback_reason TEXT,
  latency_ms INTEGER, estimated_cost_inr REAL DEFAULT 0,
  validation_status TEXT, requested_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inference_results (
  id TEXT PRIMARY KEY, request_id TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  category TEXT, urgency TEXT, language TEXT, suggested_next_action TEXT,
  confidence REAL, explanation TEXT,
  model_version TEXT, runtime_version TEXT, superseded_by TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eval_datasets (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL,
  cases TEXT NOT NULL, case_count INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eval_runs (
  id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, dataset_version INTEGER NOT NULL,
  mode TEXT NOT NULL, model_id TEXT, metrics TEXT NOT NULL,
  gates TEXT NOT NULL, breakdowns TEXT NOT NULL, verdict TEXT NOT NULL,
  started_at TEXT NOT NULL, duration_ms INTEGER
);
CREATE TABLE IF NOT EXISTS telemetry_events (
  event_id TEXT PRIMARY KEY, ts TEXT NOT NULL, tenant_id TEXT NOT NULL,
  device_id TEXT, correlation_id TEXT, model_version TEXT, runtime_version TEXT,
  policy_version INTEGER, execution_path TEXT, latency_ms INTEGER,
  success INTEGER NOT NULL, error_code TEXT, fallback_reason TEXT,
  confidence REAL, input_bytes INTEGER, output_bytes INTEGER,
  queue_state TEXT, synced INTEGER NOT NULL DEFAULT 0,
  content_preview TEXT, is_generated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS offline_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  idempotency_key TEXT UNIQUE NOT NULL,
  payload_type TEXT NOT NULL,              -- telemetry_sync | inference_job
  payload TEXT NOT NULL,                   -- json
  state TEXT NOT NULL DEFAULT 'pending',   -- pending | in_flight | synced | done | failed
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT, last_error TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY, ts TEXT NOT NULL, actor_user TEXT, role TEXT,
  tenant_id TEXT, device_id TEXT, policy_version INTEGER, model_version TEXT,
  action TEXT NOT NULL, approval_status TEXT, correlation_id TEXT,
  reason TEXT, result_summary TEXT
);
CREATE TABLE IF NOT EXISTS deployments (
  id TEXT PRIMARY KEY, model_id TEXT NOT NULL, from_version TEXT, to_version TEXT NOT NULL,
  target_device_ids TEXT NOT NULL, strategy TEXT DEFAULT 'staged',
  state TEXT NOT NULL DEFAULT 'complete', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS update_rollouts (
  id TEXT PRIMARY KEY, device_id TEXT NOT NULL, deployment_id TEXT,
  kind TEXT NOT NULL,                       -- update | rollback
  from_version TEXT, to_version TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'success',    -- staged | success | failed
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_tasks (
  id TEXT PRIMARY KEY, request_id TEXT, correlation_id TEXT, tenant_id TEXT,
  reason_code TEXT NOT NULL,               -- low_confidence | high_risk | invalid_output | stale_offline | policy_exception
  detail TEXT, original_result TEXT,       -- json
  status TEXT NOT NULL DEFAULT 'open',     -- open | resolved | rejected
  reviewer_id TEXT, resolution_note TEXT, resolved_result TEXT,
  created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cost_config (
  key TEXT PRIMARY KEY, label TEXT, value REAL NOT NULL, unit TEXT
);
"""


def connect() -> sqlite3.Connection:
    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


_conn: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = connect()
        _conn.executescript(DDL)
    return _conn


@contextmanager
def tx():
    c = db()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise


def rows(sql: str, params=()) -> list[dict]:
    return [dict(r) for r in db().execute(sql, params).fetchall()]


def row(sql: str, params=()) -> dict | None:
    r = db().execute(sql, params).fetchone()
    return dict(r) if r else None


def get_setting(key: str, default=None):
    r = row("SELECT value FROM app_settings WHERE key=?", (key,))
    return r["value"] if r else default


def set_setting(key: str, value: str):
    db().execute(
        "INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    db().commit()


def jload(s):
    return json.loads(s) if s else None


def jdump(o) -> str:
    return json.dumps(o, ensure_ascii=False)
