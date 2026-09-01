"""Receipt — immutable evidence of a WorkerRun.

Append-only. Content-addressed. No INSERT OR REPLACE.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from .spec import WorkerRun


RECEIPT_DB = "/root/mwgym/data/receipts.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (
    run_id TEXT PRIMARY KEY,
    receipt_hash TEXT NOT NULL,
    campaign_id TEXT,
    worker_id TEXT,
    worker_version TEXT,
    task_family TEXT,
    world_genome_id TEXT,
    base_sha TEXT,
    final_sha TEXT,
    success INTEGER,
    quality REAL,
    cost_usd REAL,
    latency_ms INTEGER,
    gates_passed INTEGER,
    gates_total INTEGER,
    failure_modes TEXT,
    capabilities TEXT,
    created_at REAL,
    receipt_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_receipts_campaign ON receipts(campaign_id);
CREATE INDEX IF NOT EXISTS idx_receipts_worker ON receipts(worker_id, worker_version);
CREATE INDEX IF NOT EXISTS idx_receipts_family ON receipts(task_family);
"""


def _init_db():
    Path(RECEIPT_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(RECEIPT_DB)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def record_receipt(run: WorkerRun) -> str:
    """Append an immutable receipt. Returns receipt_hash.

    If run_id already exists, this is a no-op (append-only).
    """
    _init_db()
    receipt_hash = run.compute_receipt_hash()

    conn = sqlite3.connect(RECEIPT_DB)
    # Check if already exists
    existing = conn.execute(
        "SELECT receipt_hash FROM receipts WHERE run_id=?", (run.run_id,)
    ).fetchone()
    if existing:
        conn.close()
        return existing[0]  # already recorded

    conn.execute("""
        INSERT INTO receipts
        (run_id, receipt_hash, campaign_id, worker_id, worker_version,
         task_family, world_genome_id, base_sha, final_sha,
         success, quality, cost_usd, latency_ms,
         gates_passed, gates_total, failure_modes, capabilities,
         created_at, receipt_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run.run_id, receipt_hash, run.campaign_id,
        run.worker.worker_id, run.worker.version,
        run.task_family, run.world_genome_id,
        run.base_sha, run.final_sha,
        int(run.evaluation.success), run.evaluation.quality,
        run.actual_cost_usd, run.latency_ms,
        sum(1 for g in run.evaluation.gates if g.passed),
        len(run.evaluation.gates),
        json.dumps(run.evaluation.failure_vector.modes),
        json.dumps({c.capability: c.score for c in run.evaluation.capabilities}),
        run.created_at,
        json.dumps(run.to_dict()),
    ))
    conn.commit()
    conn.close()
    return receipt_hash


def get_receipt(run_id: str) -> dict | None:
    _init_db()
    conn = sqlite3.connect(RECEIPT_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM receipts WHERE run_id=?", (run_id,)).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["failure_modes"] = json.loads(d.get("failure_modes", "[]"))
        d["capabilities"] = json.loads(d.get("capabilities", "{}"))
        return d
    return None


def get_campaign_receipts(campaign_id: str) -> list[dict]:
    _init_db()
    conn = sqlite3.connect(RECEIPT_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM receipts WHERE campaign_id=? ORDER BY created_at",
        (campaign_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def receipt_summary(campaign_id: str) -> dict:
    _init_db()
    conn = sqlite3.connect(RECEIPT_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("""
        SELECT COUNT(*) as n,
               SUM(success) as pass,
               AVG(quality) as avg_q,
               AVG(cost_usd) as avg_c,
               AVG(latency_ms) as avg_lat
        FROM receipts WHERE campaign_id=?
    """, (campaign_id,)).fetchone()
    conn.close()
    return {
        "campaign_id": campaign_id,
        "total_runs": row["n"],
        "passed": row["pass"] or 0,
        "avg_quality": row["avg_q"] or 0,
        "avg_cost": row["avg_c"] or 0,
        "avg_latency_ms": row["avg_lat"] or 0,
    }
