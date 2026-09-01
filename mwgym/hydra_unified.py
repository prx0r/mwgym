"""UnifiedHydra — single SQLite store for all MWGym + CGE data.

Merges:
- hydra.db (old LabProjection: lab_runs, lab_insights, lab_experiments)
- hydradb.db (GraphStore: hydra_nodes, hydra_edges)

Into one clean schema that supports:
- Worker runs with FailureVectors
- World genome evolution tracking
- Capability evidence accumulation
- Curriculum provenance
- Graph relationships
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .schema.world import FailureVector, WorldGenome


DEFAULT_DB = "/root/mwgym/data/unified_hydra.db"

SCHEMA_SQL = """
-- Worker runs (replaces lab_runs)
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    world_genome_id TEXT,
    worker_genome_id TEXT,
    family_id TEXT,
    task_family TEXT,

    -- Worker
    harness TEXT,
    model TEXT,
    provider TEXT,

    -- Execution
    started_at REAL,
    duration_ms INTEGER,
    model_calls INTEGER DEFAULT 0,
    tool_calls INTEGER DEFAULT 0,

    -- Cost
    cost_usd REAL DEFAULT 0.0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,

    -- Outcome
    success INTEGER DEFAULT 0,
    quality_score REAL DEFAULT 0.0,
    correctness REAL DEFAULT 0.0,
    completeness REAL DEFAULT 0.0,
    efficiency REAL DEFAULT 0.0,
    reward_usd REAL DEFAULT 0.0,

    -- Failure vector (JSON)
    failure_vector TEXT DEFAULT '{}',

    -- Artifacts
    output_hash TEXT,
    artifact_hashes TEXT DEFAULT '[]',

    -- Provenance
    experiment_id TEXT,
    parent_run_id TEXT,
    metadata TEXT DEFAULT '{}'
);

-- World genomes (CGE evolution)
CREATE TABLE IF NOT EXISTS world_genomes (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    generation INTEGER DEFAULT 0,
    family_id TEXT,
    difficulty INTEGER DEFAULT 1,
    seed INTEGER DEFAULT 0,

    -- World structure (JSON)
    structure TEXT DEFAULT '{}',
    information TEXT DEFAULT '{}',
    resources TEXT DEFAULT '{}',
    dynamics TEXT DEFAULT '{}',
    perturbations TEXT DEFAULT '{}',
    evaluator TEXT DEFAULT '{}',

    -- Stats
    n_runs INTEGER DEFAULT 0,
    mean_quality REAL DEFAULT 0.0,
    mean_cost_usd REAL DEFAULT 0.0,
    mean_duration_ms REAL DEFAULT 0.0,
    worker_success_rate REAL DEFAULT 0.0,
    reference_success_rate REAL DEFAULT 0.0,
    discriminative_power REAL DEFAULT 0.0,

    -- Provenance
    created_at REAL,
    promoted INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}'
);

-- Worker genomes
CREATE TABLE IF NOT EXISTS worker_genomes (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    generation INTEGER DEFAULT 0,
    harness TEXT,
    model TEXT,

    -- Config (JSON)
    config TEXT DEFAULT '{}',

    -- Stats
    n_runs INTEGER DEFAULT 0,
    mean_quality REAL DEFAULT 0.0,
    mean_cost_usd REAL DEFAULT 0.0,
    capability_scores TEXT DEFAULT '{}',

    -- Provenance
    created_at REAL,
    promoted INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}'
);

-- Capability evidence (per worker × family × capability)
CREATE TABLE IF NOT EXISTS capability_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_genome_id TEXT,
    family_id TEXT,
    capability TEXT,

    -- Running stats
    n_samples INTEGER DEFAULT 0,
    mean_score REAL DEFAULT 0.0,
    variance REAL DEFAULT 0.0,
    last_score REAL DEFAULT 0.0,

    -- Timestamps
    last_updated REAL,
    UNIQUE(worker_genome_id, family_id, capability)
);

-- Failure mode tracking (per family × mode)
CREATE TABLE IF NOT EXISTS failure_modes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id TEXT,
    failure_mode TEXT,

    -- Stats
    n_occurrences INTEGER DEFAULT 0,
    n_total_runs INTEGER DEFAULT 0,
    frequency REAL DEFAULT 0.0,

    -- Weakness association
    weakest_worker TEXT,
    severity REAL DEFAULT 0.0,

    last_updated REAL,
    UNIQUE(family_id, failure_mode)
);

-- Curriculum archive (MAP-Elites style)
CREATE TABLE IF NOT EXISTS curriculum_archive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id TEXT,
    niche_key TEXT,          -- e.g. "stale_data×cheap×low_budget"

    -- Best world for this niche
    world_genome_id TEXT,
    difficulty INTEGER,
    discriminative_power REAL,
    worker_success_rate REAL,

    -- Stats
    n_replays INTEGER DEFAULT 0,
    last_replay_at REAL,

    created_at REAL,
    UNIQUE(family_id, niche_key)
);

-- Experiments
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    hypothesis TEXT,
    family_id TEXT,
    status TEXT DEFAULT 'running',
    config TEXT DEFAULT '{}',
    results TEXT DEFAULT '{}',
    created_at REAL,
    completed_at REAL
);

-- Insights (flexible findings)
CREATE TABLE IF NOT EXISTS insights (
    insight_id TEXT PRIMARY KEY,
    experiment_id TEXT,
    kind TEXT,
    title TEXT,
    body TEXT,
    evidence_runs INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.0,
    created_at REAL
);

-- Graph nodes (unified from GraphStore)
CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    properties TEXT DEFAULT '{}',
    created_at REAL
);

-- Graph edges
CREATE TABLE IF NOT EXISTS graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    type TEXT NOT NULL,
    properties TEXT DEFAULT '{}',
    created_at REAL
);

-- ─── Metaculus Forecast Tracking ─────────────────────────────────────

-- Forecasts (every submission to Metaculus)
CREATE TABLE IF NOT EXISTS forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    question_title TEXT,
    question_type TEXT,          -- binary, numeric, multiple_choice
    
    -- Our forecast
    forecast_value TEXT,         -- JSON: float for binary, list for numeric, dict for MC
    forecast_submitted INTEGER DEFAULT 0,
    submission_time REAL,
    
    -- Community state at submission
    community_prediction REAL,
    nr_forecasters INTEGER DEFAULT 0,
    
    -- Question metadata
    close_time TEXT,
    resolve_time TEXT,
    tournament TEXT,
    
    -- Worker that made this forecast
    worker_genome_id TEXT,
    run_id TEXT,
    
    -- Outcome (filled when question resolves)
    resolved INTEGER DEFAULT 0,
    resolution_value TEXT,       -- actual outcome
    our_score REAL,              -- our Brier/log score
    community_score REAL,        -- community's score
    beat_community INTEGER,      -- 1 if we beat community
    
    -- Provenance
    created_at REAL,
    updated_at REAL,
    metadata TEXT DEFAULT '{}'
);

-- Forecast sessions (groups of forecasts in one run)
CREATE TABLE IF NOT EXISTS forecast_sessions (
    session_id TEXT PRIMARY KEY,
    worker_genome_id TEXT,
    run_id TEXT,
    
    -- Stats
    n_questions INTEGER DEFAULT 0,
    n_submitted INTEGER DEFAULT 0,
    n_resolved INTEGER DEFAULT 0,
    n_beat_community INTEGER DEFAULT 0,
    
    -- Scores
    mean_brier REAL,
    mean_log_score REAL,
    total_reward_usd REAL DEFAULT 0.0,
    
    -- Timing
    started_at REAL,
    completed_at REAL,
    metadata TEXT DEFAULT '{}'
);

-- Forecast learning (what we learned from each resolution)
CREATE TABLE IF NOT EXISTS forecast_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    lesson_type TEXT,            -- calibration, base_rate, update_timing, etc.
    lesson TEXT,
    evidence TEXT,               -- JSON with specific data points
    confidence REAL DEFAULT 0.5,
    
    -- Which worker/method this applies to
    worker_genome_id TEXT,
    family_id TEXT,
    
    created_at REAL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_runs_world ON runs(world_genome_id);
CREATE INDEX IF NOT EXISTS idx_runs_worker ON runs(worker_genome_id);
CREATE INDEX IF NOT EXISTS idx_runs_family ON runs(family_id);
CREATE INDEX IF NOT EXISTS idx_runs_experiment ON runs(experiment_id);
CREATE INDEX IF NOT EXISTS idx_world_genomes_family ON world_genomes(family_id);
CREATE INDEX IF NOT EXISTS idx_capability_evidence_worker ON capability_evidence(worker_genome_id);
CREATE INDEX IF NOT EXISTS idx_capability_evidence_family ON capability_evidence(family_id);
CREATE INDEX IF NOT EXISTS idx_failure_modes_family ON failure_modes(family_id);
CREATE INDEX IF NOT EXISTS idx_curriculum_family ON curriculum_archive(family_id);
CREATE INDEX IF NOT EXISTS idx_curriculum_niche ON curriculum_archive(family_id, niche_key);
CREATE INDEX IF NOT EXISTS idx_forecasts_question ON forecasts(question_id);
CREATE INDEX IF NOT EXISTS idx_forecasts_worker ON forecasts(worker_genome_id);
CREATE INDEX IF NOT EXISTS idx_forecasts_resolved ON forecasts(resolved);
CREATE INDEX IF NOT EXISTS idx_forecast_sessions_worker ON forecast_sessions(worker_genome_id);
"""


class UnifiedHydra:
    """Single entry point for all MWGym data persistence.

    SQLite-only. No Docker. No external services.
    """

    def __init__(self, db_path: str = DEFAULT_DB):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ─── Runs ──────────────────────────────────────────────────────────

    def record_run(self, run_id: str, world_genome_id: str = "",
                   worker_genome_id: str = "", family_id: str = "",
                   harness: str = "", model: str = "", provider: str = "",
                   cost_usd: float = 0.0, duration_ms: int = 0,
                   model_calls: int = 0, tool_calls: int = 0,
                   prompt_tokens: int = 0, completion_tokens: int = 0,
                   reasoning_tokens: int = 0,
                   success: bool = False, quality_score: float = 0.0,
                   correctness: float = 0.0, completeness: float = 0.0,
                   efficiency: float = 0.0, reward_usd: float = 0.0,
                   output_hash: str = "", experiment_id: str = "",
                   failure_vector: FailureVector | None = None,
                   metadata: dict | None = None):
        fv_json = json.dumps(failure_vector.to_dict()) if failure_vector else "{}"
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO runs
            (run_id, world_genome_id, worker_genome_id, family_id,
             harness, model, provider, started_at, duration_ms,
             model_calls, tool_calls, cost_usd,
             prompt_tokens, completion_tokens, reasoning_tokens,
             success, quality_score, correctness, completeness, efficiency,
             reward_usd, output_hash, failure_vector, experiment_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_id, world_genome_id, worker_genome_id, family_id,
              harness, model, provider, time.time(), duration_ms,
              model_calls, tool_calls, cost_usd,
              prompt_tokens, completion_tokens, reasoning_tokens,
              int(success), quality_score, correctness, completeness, efficiency,
              reward_usd, output_hash, fv_json, experiment_id,
              json.dumps(metadata or {})))
        conn.commit()
        conn.close()

    def get_run(self, run_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        conn.close()
        if row:
            d = dict(row)
            d["failure_vector"] = json.loads(d.get("failure_vector", "{}"))
            d["metadata"] = json.loads(d.get("metadata", "{}"))
            d["artifact_hashes"] = json.loads(d.get("artifact_hashes", "[]"))
            return d
        return None

    def get_runs(self, family_id: str = "", worker_genome_id: str = "",
                 world_genome_id: str = "", experiment_id: str = "",
                 limit: int = 100) -> list[dict]:
        conn = self._conn()
        query = "SELECT * FROM runs WHERE 1=1"
        params = []
        if family_id:
            query += " AND family_id=?"
            params.append(family_id)
        if worker_genome_id:
            query += " AND worker_genome_id=?"
            params.append(worker_genome_id)
        if world_genome_id:
            query += " AND world_genome_id=?"
            params.append(world_genome_id)
        if experiment_id:
            query += " AND experiment_id=?"
            params.append(experiment_id)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        results = []
        for row in rows:
            d = dict(row)
            d["failure_vector"] = json.loads(d.get("failure_vector", "{}"))
            d["metadata"] = json.loads(d.get("metadata", "{}"))
            results.append(d)
        return results

    # ─── World Genomes ─────────────────────────────────────────────────

    def record_world_genome(self, genome: WorldGenome):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO world_genomes
            (id, parent_id, generation, family_id, difficulty, seed,
             structure, information, resources, dynamics, perturbations, evaluator,
             created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (genome.id, genome.parent_id, genome.generation, genome.family_id,
              genome.difficulty, genome.seed,
              json.dumps(genome.structure), json.dumps(genome.information),
              json.dumps(genome.resources), json.dumps(genome.dynamics),
              json.dumps(genome.perturbations), json.dumps(genome.evaluator),
              genome.created_at, json.dumps(genome.provenance)))
        conn.commit()
        conn.close()

    def get_world_genome(self, genome_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute("SELECT * FROM world_genomes WHERE id=?", (genome_id,)).fetchone()
        conn.close()
        if row:
            d = dict(row)
            for key in ("structure", "information", "resources", "dynamics",
                        "perturbations", "evaluator", "metadata"):
                d[key] = json.loads(d.get(key, "{}"))
            return d
        return None

    def update_world_genome_stats(self, genome_id: str, n_runs: int,
                                   mean_quality: float, mean_cost_usd: float,
                                   mean_duration_ms: float,
                                   worker_success_rate: float,
                                   reference_success_rate: float = 0.0,
                                   discriminative_power: float = 0.0):
        conn = self._conn()
        conn.execute("""
            UPDATE world_genomes SET
                n_runs=?, mean_quality=?, mean_cost_usd=?, mean_duration_ms=?,
                worker_success_rate=?, reference_success_rate=?, discriminative_power=?
            WHERE id=?
        """, (n_runs, mean_quality, mean_cost_usd, mean_duration_ms,
              worker_success_rate, reference_success_rate, discriminative_power,
              genome_id))
        conn.commit()
        conn.close()

    def get_world_genomes(self, family_id: str = "", promoted_only: bool = False,
                           limit: int = 50) -> list[dict]:
        conn = self._conn()
        query = "SELECT * FROM world_genomes WHERE 1=1"
        params = []
        if family_id:
            query += " AND family_id=?"
            params.append(family_id)
        if promoted_only:
            query += " AND promoted=1"
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        results = []
        for row in rows:
            d = dict(row)
            for key in ("structure", "information", "resources", "dynamics",
                        "perturbations", "evaluator", "metadata"):
                d[key] = json.loads(d.get(key, "{}"))
            results.append(d)
        return results

    # ─── Worker Genomes ────────────────────────────────────────────────

    def record_worker_genome(self, genome_id: str, parent_id: str = "",
                              generation: int = 0, harness: str = "",
                              model: str = "", config: dict | None = None):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO worker_genomes
            (id, parent_id, generation, harness, model, config, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (genome_id, parent_id, generation, harness, model,
              json.dumps(config or {}), time.time()))
        conn.commit()
        conn.close()

    def get_worker_genome(self, genome_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute("SELECT * FROM worker_genomes WHERE id=?", (genome_id,)).fetchone()
        conn.close()
        if row:
            d = dict(row)
            d["config"] = json.loads(d.get("config", "{}"))
            d["capability_scores"] = json.loads(d.get("capability_scores", "{}"))
            return d
        return None

    # ─── Capability Evidence ───────────────────────────────────────────

    def record_capability(self, worker_genome_id: str, family_id: str,
                           capability: str, score: float):
        conn = self._conn()
        row = conn.execute("""
            SELECT n_samples, mean_score, variance FROM capability_evidence
            WHERE worker_genome_id=? AND family_id=? AND capability=?
        """, (worker_genome_id, family_id, capability)).fetchone()

        now = time.time()
        if row:
            n = row["n_samples"] + 1
            old_mean = row["mean_score"]
            new_mean = old_mean + (score - old_mean) / n
            # Welford's online variance
            old_var = row["variance"]
            new_var = old_var + (score - old_mean) * (score - new_mean)
            conn.execute("""
                UPDATE capability_evidence SET
                    n_samples=?, mean_score=?, variance=?, last_score=?, last_updated=?
                WHERE worker_genome_id=? AND family_id=? AND capability=?
            """, (n, new_mean, new_var, score, now,
                  worker_genome_id, family_id, capability))
        else:
            conn.execute("""
                INSERT INTO capability_evidence
                (worker_genome_id, family_id, capability, n_samples, mean_score,
                 variance, last_score, last_updated)
                VALUES (?, ?, ?, 1, ?, 0.0, ?, ?)
            """, (worker_genome_id, family_id, capability, score, score, now))
        conn.commit()
        conn.close()

    def get_capabilities(self, worker_genome_id: str,
                          family_id: str = "") -> list[dict]:
        conn = self._conn()
        query = "SELECT * FROM capability_evidence WHERE worker_genome_id=?"
        params = [worker_genome_id]
        if family_id:
            query += " AND family_id=?"
            params.append(family_id)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ─── Failure Modes ─────────────────────────────────────────────────

    def record_failure_mode(self, family_id: str, failure_mode: str,
                             severity: float = 0.0, worker_id: str = ""):
        conn = self._conn()
        now = time.time()
        row = conn.execute("""
            SELECT n_occurrences, n_total_runs FROM failure_modes
            WHERE family_id=? AND failure_mode=?
        """, (family_id, failure_mode)).fetchone()

        if row:
            new_n = row["n_occurrences"] + 1
            new_total = row["n_total_runs"] + 1
            new_freq = new_n / new_total
            conn.execute("""
                UPDATE failure_modes SET
                    n_occurrences=?, n_total_runs=?,
                    frequency=?, severity=?, weakest_worker=?,
                    last_updated=?
                WHERE family_id=? AND failure_mode=?
            """, (new_n, new_total, new_freq, severity, worker_id, now,
                  family_id, failure_mode))
        else:
            conn.execute("""
                INSERT INTO failure_modes
                (family_id, failure_mode, n_occurrences, n_total_runs,
                 frequency, severity, weakest_worker, last_updated)
                VALUES (?, ?, 1, 1, ?, ?, ?, ?)
            """, (family_id, failure_mode, 1.0, severity, worker_id, now))
        conn.commit()
        conn.close()

    def get_failure_modes(self, family_id: str,
                           min_frequency: float = 0.0) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("""
            SELECT * FROM failure_modes
            WHERE family_id=? AND frequency >= ?
            ORDER BY frequency DESC
        """, (family_id, min_frequency)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ─── Curriculum Archive (MAP-Elites) ───────────────────────────────

    def record_curriculum(self, family_id: str, niche_key: str,
                           world_genome_id: str, difficulty: int,
                           discriminative_power: float = 0.0,
                           worker_success_rate: float = 0.0):
        conn = self._conn()
        now = time.time()
        conn.execute("""
            INSERT OR REPLACE INTO curriculum_archive
            (family_id, niche_key, world_genome_id, difficulty,
             discriminative_power, worker_success_rate, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (family_id, niche_key, world_genome_id, difficulty,
              discriminative_power, worker_success_rate, now))
        conn.commit()
        conn.close()

    def get_curriculum(self, family_id: str,
                        niche_key: str = "") -> list[dict]:
        conn = self._conn()
        query = "SELECT * FROM curriculum_archive WHERE family_id=?"
        params = [family_id]
        if niche_key:
            query += " AND niche_key=?"
            params.append(niche_key)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ─── Experiments ───────────────────────────────────────────────────

    def record_experiment(self, experiment_id: str, hypothesis: str = "",
                           family_id: str = "", status: str = "running",
                           config: dict | None = None):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO experiments
            (experiment_id, hypothesis, family_id, status, config, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (experiment_id, hypothesis, family_id, status,
              json.dumps(config or {}), time.time()))
        conn.commit()
        conn.close()

    def complete_experiment(self, experiment_id: str, results: dict | None = None):
        conn = self._conn()
        conn.execute("""
            UPDATE experiments SET status='completed', completed_at=?, results=?
            WHERE experiment_id=?
        """, (time.time(), json.dumps(results or {}), experiment_id))
        conn.commit()
        conn.close()

    # ─── Insights ──────────────────────────────────────────────────────

    def add_insight(self, insight_id: str, title: str, body: str = "",
                     kind: str = "", experiment_id: str = "",
                     evidence_runs: int = 0, confidence: float = 0.0):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO insights
            (insight_id, experiment_id, kind, title, body, evidence_runs,
             confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (insight_id, experiment_id, kind, title, body,
              evidence_runs, confidence, time.time()))
        conn.commit()
        conn.close()

    # ─── Graph ─────────────────────────────────────────────────────────

    def add_node(self, node_id: str, label: str, properties: dict | None = None):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO graph_nodes (id, label, properties, created_at)
            VALUES (?, ?, ?, ?)
        """, (node_id, label, json.dumps(properties or {}), time.time()))
        conn.commit()
        conn.close()

    def add_edge(self, src: str, dst: str, edge_type: str,
                  properties: dict | None = None):
        conn = self._conn()
        conn.execute("""
            INSERT INTO graph_edges (source_id, target_id, type, properties, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (src, dst, edge_type, json.dumps(properties or {}), time.time()))
        conn.commit()
        conn.close()

    def get_edges_from(self, node_id: str, edge_type: str = "") -> list[dict]:
        conn = self._conn()
        if edge_type:
            rows = conn.execute(
                "SELECT * FROM graph_edges WHERE source_id=? AND type=?",
                (node_id, edge_type)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM graph_edges WHERE source_id=?",
                (node_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ─── Aggregate Queries ─────────────────────────────────────────────

    def family_stats(self, family_id: str) -> dict:
        """Get aggregate stats for a family."""
        conn = self._conn()
        runs = conn.execute(
            "SELECT COUNT(*) as n, AVG(quality_score) as q, AVG(cost_usd) as c "
            "FROM runs WHERE family_id=?", (family_id,)).fetchone()
        worlds = conn.execute(
            "SELECT COUNT(*) as n FROM world_genomes WHERE family_id=?",
            (family_id,)).fetchone()
        failures = conn.execute(
            "SELECT failure_mode, frequency FROM failure_modes "
            "WHERE family_id=? ORDER BY frequency DESC LIMIT 5",
            (family_id,)).fetchall()
        conn.close()
        return {
            "family_id": family_id,
            "total_runs": runs["n"] if runs else 0,
            "mean_quality": runs["q"] if runs else 0.0,
            "mean_cost_usd": runs["c"] if runs else 0.0,
            "total_worlds": worlds["n"] if worlds else 0,
            "top_failures": [{"mode": f["failure_mode"], "freq": f["frequency"]}
                            for f in failures],
        }

    def worker_vs_worker(self, worker_a: str, worker_b: str,
                          family_id: str = "") -> dict:
        """Compare two worker genomes."""
        conn = self._conn()
        query_a = "SELECT AVG(quality_score) as q, AVG(cost_usd) as c, COUNT(*) as n " \
                   "FROM runs WHERE worker_genome_id=?"
        query_b = query_a
        params_a = [worker_a]
        params_b = [worker_b]
        if family_id:
            query_a += " AND family_id=?"
            query_b += " AND family_id=?"
            params_a.append(family_id)
            params_b.append(family_id)

        a = conn.execute(query_a, params_a).fetchone()
        b = conn.execute(query_b, params_b).fetchone()
        conn.close()
        return {
            "worker_a": {"id": worker_a, "quality": a["q"], "cost": a["c"], "n": a["n"]} if a else {},
            "worker_b": {"id": worker_b, "quality": b["q"], "cost": b["c"], "n": b["n"]} if b else {},
        }

    def summary(self) -> dict:
        """Get overall lab summary."""
        conn = self._conn()
        runs = conn.execute("SELECT COUNT(*) as n FROM runs").fetchone()
        worlds = conn.execute("SELECT COUNT(*) as n FROM world_genomes").fetchone()
        workers = conn.execute("SELECT COUNT(*) as n FROM worker_genomes").fetchone()
        experiments = conn.execute("SELECT COUNT(*) as n FROM experiments").fetchone()
        forecasts = conn.execute("SELECT COUNT(*) as n FROM forecasts").fetchone()
        resolved = conn.execute("SELECT COUNT(*) as n FROM forecasts WHERE resolved=1").fetchone()
        beat = conn.execute("SELECT COUNT(*) as n FROM forecasts WHERE beat_community=1").fetchone()
        conn.close()
        return {
            "total_runs": runs["n"] if runs else 0,
            "total_worlds": worlds["n"] if worlds else 0,
            "total_workers": workers["n"] if workers else 0,
            "total_experiments": experiments["n"] if experiments else 0,
            "total_forecasts": forecasts["n"] if forecasts else 0,
            "resolved_forecasts": resolved["n"] if resolved else 0,
            "beat_community": beat["n"] if beat else 0,
        }

    # ─── Metaculus Forecast Tracking ──────────────────────────────────

    def record_forecast(self, question_id: int, question_title: str = "",
                        question_type: str = "binary", forecast_value: Any = None,
                        submitted: bool = False, community_prediction: float = None,
                        nr_forecasters: int = 0, close_time: str = "",
                        tournament: str = "", worker_genome_id: str = "",
                        run_id: str = "") -> int:
        """Record a forecast submission to Metaculus."""
        conn = self._conn()
        now = time.time()
        cursor = conn.execute("""
            INSERT INTO forecasts
            (question_id, question_title, question_type, forecast_value,
             forecast_submitted, submission_time, community_prediction,
             nr_forecasters, close_time, tournament, worker_genome_id,
             run_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (question_id, question_title, question_type,
              json.dumps(forecast_value) if forecast_value is not None else None,
              1 if submitted else 0, now, community_prediction,
              nr_forecasters, close_time, tournament, worker_genome_id,
              run_id, now, now))
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return row_id

    def record_forecast_resolution(self, question_id: int, resolution_value: str,
                                    our_forecast: float, community_forecast: float) -> dict:
        """Record when a Metaculus question resolves.
        
        Returns score comparison.
        """
        conn = self._conn()
        
        # Calculate Brier scores (lower is better)
        try:
            res = float(resolution_value) if resolution_value in ("Yes", "1", "True") else 0.0
        except:
            res = 0.0
        
        our_brier = (our_forecast - res) ** 2
        comm_brier = (community_forecast - res) ** 2
        beat = our_brier < comm_brier
        
        conn.execute("""
            UPDATE forecasts SET
                resolved = 1,
                resolution_value = ?,
                our_score = ?,
                community_score = ?,
                beat_community = ?,
                updated_at = ?
            WHERE question_id = ?
        """, (resolution_value, our_brier, comm_brier, 1 if beat else 0,
              time.time(), question_id))
        
        conn.commit()
        conn.close()
        
        return {
            "question_id": question_id,
            "resolution": resolution_value,
            "our_brier": our_brier,
            "community_brier": comm_brier,
            "beat_community": beat,
        }

    def record_forecast_session(self, session_id: str, worker_genome_id: str = "",
                                 run_id: str = "", n_questions: int = 0,
                                 n_submitted: int = 0) -> None:
        """Record a forecast session (batch of forecasts)."""
        conn = self._conn()
        conn.execute("""
            INSERT INTO forecast_sessions
            (session_id, worker_genome_id, run_id, n_questions, n_submitted,
             started_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, worker_genome_id, run_id, n_questions, n_submitted,
              time.time()))
        conn.commit()
        conn.close()

    def update_forecast_session(self, session_id: str, **kwargs) -> None:
        """Update a forecast session with results."""
        conn = self._conn()
        sets = []
        params = []
        for k, v in kwargs.items():
            if k in ("n_resolved", "n_beat_community", "mean_brier", "mean_log_score",
                      "total_reward_usd", "completed_at"):
                sets.append(f"{k} = ?")
                params.append(v)
        if sets:
            params.append(session_id)
            conn.execute(f"UPDATE forecast_sessions SET {', '.join(sets)} WHERE session_id = ?", params)
            conn.commit()
        conn.close()

    def get_unresolved_forecasts(self, limit: int = 100) -> list[dict]:
        """Get forecasts that haven't resolved yet."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM forecasts WHERE resolved=0 ORDER BY submission_time DESC LIMIT ?",
            (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_forecast_stats(self, worker_genome_id: str = None) -> dict:
        """Get forecasting performance stats."""
        conn = self._conn()
        if worker_genome_id:
            total = conn.execute("SELECT COUNT(*) as n FROM forecasts WHERE worker_genome_id=?", (worker_genome_id,)).fetchone()
            resolved = conn.execute("SELECT COUNT(*) as n FROM forecasts WHERE worker_genome_id=? AND resolved=1", (worker_genome_id,)).fetchone()
            beat = conn.execute("SELECT COUNT(*) as n FROM forecasts WHERE worker_genome_id=? AND beat_community=1", (worker_genome_id,)).fetchone()
            avg_brier = conn.execute("SELECT AVG(our_score) as avg FROM forecasts WHERE worker_genome_id=? AND resolved=1", (worker_genome_id,)).fetchone()
        else:
            total = conn.execute("SELECT COUNT(*) as n FROM forecasts").fetchone()
            resolved = conn.execute("SELECT COUNT(*) as n FROM forecasts WHERE resolved=1").fetchone()
            beat = conn.execute("SELECT COUNT(*) as n FROM forecasts WHERE beat_community=1").fetchone()
            avg_brier = conn.execute("SELECT AVG(our_score) as avg FROM forecasts WHERE resolved=1").fetchone()
        conn.close()
        
        t = total["n"] if total else 0
        r = resolved["n"] if resolved else 0
        b = beat["n"] if beat else 0
        avg = avg_brier["avg"] if avg_brier else None
        
        return {
            "total_forecasts": t,
            "resolved": r,
            "pending": t - r,
            "beat_community": b,
            "beat_rate": b / max(1, r),
            "mean_brier": avg,
            "calibration": "good" if avg and avg < 0.25 else "needs_improvement",
        }

    def record_forecast_lesson(self, question_id: int, lesson_type: str,
                                lesson: str, evidence: dict = None,
                                worker_genome_id: str = "", confidence: float = 0.5) -> None:
        """Record a lesson learned from a forecast resolution."""
        conn = self._conn()
        conn.execute("""
            INSERT INTO forecast_lessons
            (question_id, lesson_type, lesson, evidence, confidence,
             worker_genome_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (question_id, lesson_type, lesson,
              json.dumps(evidence or {}), confidence,
              worker_genome_id, time.time()))
        conn.commit()
        conn.close()

    def get_forecast_lessons(self, lesson_type: str = None, limit: int = 50) -> list[dict]:
        """Get forecasting lessons for improving future forecasts."""
        conn = self._conn()
        if lesson_type:
            rows = conn.execute(
                "SELECT * FROM forecast_lessons WHERE lesson_type=? ORDER BY confidence DESC LIMIT ?",
                (lesson_type, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM forecast_lessons ORDER BY confidence DESC LIMIT ?",
                (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
