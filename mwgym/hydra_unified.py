"""UnifiedHydra — single SQLite store for all MWGym data.

This is the canonical store for:
- runs
- world_genomes
- worker_genomes
- capability_evidence
- failure_modes
- curriculum_archive
- experiments
- insights
- graph_nodes
- graph_edges
- trajectories
- forecasts
- forecast_sessions
- forecast_lessons
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class UnifiedHydra:
    """Single SQLite store for all MWGym data."""

    def __init__(self, db_path: str = ""):
        if not db_path:
            db_path = str(Path(__file__).parent / "data" / "unified_hydra.db")
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                world_genome_id TEXT,
                worker_genome_id TEXT,
                family_id TEXT,
                harness TEXT,
                model TEXT,
                cost_usd REAL DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                model_calls INTEGER DEFAULT 0,
                success INTEGER DEFAULT 0,
                quality_score REAL DEFAULT 0,
                failure_vector TEXT,
                experiment_id TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS world_genomes (
                id TEXT PRIMARY KEY,
                family_id TEXT,
                difficulty INTEGER DEFAULT 1,
                seed INTEGER DEFAULT 0,
                structure TEXT,
                information TEXT,
                resources TEXT,
                n_runs INTEGER DEFAULT 0,
                mean_quality REAL DEFAULT 0,
                mean_cost_usd REAL DEFAULT 0,
                mean_duration_ms REAL DEFAULT 0,
                success_rate REAL DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS worker_genomes (
                id TEXT PRIMARY KEY,
                harness TEXT,
                model TEXT,
                n_runs INTEGER DEFAULT 0,
                mean_quality REAL DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS capability_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_genome_id TEXT,
                family_id TEXT,
                capability TEXT,
                n_samples INTEGER DEFAULT 0,
                mean_score REAL DEFAULT 0,
                variance REAL DEFAULT 0,
                last_score REAL DEFAULT 0,
                last_updated REAL,
                UNIQUE(worker_genome_id, family_id, capability)
            );
            CREATE TABLE IF NOT EXISTS failure_modes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_id TEXT,
                failure_mode TEXT,
                n_occurrences INTEGER DEFAULT 0,
                n_total_runs INTEGER DEFAULT 0,
                frequency REAL DEFAULT 0,
                weakest_worker TEXT,
                severity REAL DEFAULT 0,
                last_updated REAL,
                UNIQUE(family_id, failure_mode)
            );
            CREATE TABLE IF NOT EXISTS curriculum_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_id TEXT,
                niche_key TEXT,
                world_genome_id TEXT,
                difficulty INTEGER,
                discriminative_power REAL DEFAULT 0,
                worker_success_rate REAL DEFAULT 0,
                created_at REAL,
                UNIQUE(family_id, niche_key, world_genome_id)
            );
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                hypothesis TEXT,
                family_id TEXT,
                status TEXT DEFAULT 'running',
                config TEXT,
                results TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS insights (
                insight_id TEXT PRIMARY KEY,
                experiment_id TEXT,
                kind TEXT,
                title TEXT,
                body TEXT,
                evidence_runs INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY,
                label TEXT,
                properties TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS graph_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT,
                target_id TEXT,
                edge_type TEXT,
                properties TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS trajectories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                events TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id TEXT,
                worker_id TEXT,
                prediction REAL,
                submitted_at REAL,
                brier_score REAL,
                log_score REAL,
                status TEXT DEFAULT 'pending',
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS forecast_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                n_forecasts INTEGER DEFAULT 0,
                n_submitted INTEGER DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS forecast_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                lesson_type TEXT,
                lesson TEXT,
                confidence REAL DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
        """)
        conn.commit()
        conn.close()

    # ─── Runs ─────────────────────────────────────────────────────────

    def record_run(self, run_id: str, world_genome_id: str = "",
                   worker_genome_id: str = "", family_id: str = "",
                   harness: str = "", model: str = "", cost_usd: float = 0,
                   duration_ms: int = 0, model_calls: int = 0,
                   success: bool = False, quality_score: float = 0,
                   failure_vector=None, experiment_id: str = ""):
        conn = self._conn()
        fv_json = ""
        if failure_vector:
            fv_json = json.dumps(failure_vector.to_dict() if hasattr(failure_vector, 'to_dict') else failure_vector)
        conn.execute("""
            INSERT OR REPLACE INTO runs
            (run_id, world_genome_id, worker_genome_id, family_id, harness, model,
             cost_usd, duration_ms, model_calls, success, quality_score,
             failure_vector, experiment_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_id, world_genome_id, worker_genome_id, family_id, harness, model,
              cost_usd, duration_ms, model_calls, 1 if success else 0, quality_score,
              fv_json, experiment_id, time.time()))
        conn.commit()
        conn.close()

    def get_runs(self, world_genome_id: str = "", family_id: str = "",
                 limit: int = 100) -> list[dict]:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM runs WHERE 1=1"
        params = []
        if world_genome_id:
            query += " AND world_genome_id = ?"
            params.append(world_genome_id)
        if family_id:
            query += " AND family_id = ?"
            params.append(family_id)
        query += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ─── World Genomes ────────────────────────────────────────────────

    def record_world_genome(self, genome):
        conn = self._conn()
        d = genome.to_dict() if hasattr(genome, 'to_dict') else genome
        conn.execute("""
            INSERT OR REPLACE INTO world_genomes
            (id, family_id, difficulty, seed, structure, information, resources, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (d.get("id", ""), d.get("family_id", ""), d.get("difficulty", 1),
              d.get("seed", 0), json.dumps(d.get("structure", {})),
              json.dumps(d.get("information", {})), json.dumps(d.get("resources", {})),
              time.time()))
        conn.commit()
        conn.close()

    def get_world_genome(self, genome_id: str) -> dict | None:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM world_genomes WHERE id = ?", (genome_id,)).fetchone()
        conn.close()
        if row:
            d = dict(row)
            # Parse JSON fields
            for field in ["structure", "information", "resources"]:
                if d.get(field) and isinstance(d[field], str):
                    try:
                        d[field] = json.loads(d[field])
                    except (json.JSONDecodeError, TypeError):
                        d[field] = {}
            return d
        return None

    def update_world_genome_stats(self, genome_id: str, n_runs: int,
                                   mean_quality: float, mean_cost: float,
                                   mean_duration: float, success_rate: float):
        conn = self._conn()
        conn.execute("""
            UPDATE world_genomes SET n_runs=?, mean_quality=?, mean_cost_usd=?,
            mean_duration_ms=?, success_rate=? WHERE id=?
        """, (n_runs, mean_quality, mean_cost, mean_duration, success_rate, genome_id))
        conn.commit()
        conn.close()

    # ─── Worker Genomes ───────────────────────────────────────────────

    def record_worker_genome(self, genome_id: str, harness: str = "",
                             model: str = ""):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO worker_genomes (id, harness, model, created_at)
            VALUES (?, ?, ?, ?)
        """, (genome_id, harness, model, time.time()))
        conn.commit()
        conn.close()

    # ─── Capability Evidence ──────────────────────────────────────────

    def record_capability(self, worker_genome_id: str, family_id: str,
                          capability: str, score: float):
        conn = self._conn()
        conn.execute("""
            INSERT INTO capability_evidence
            (worker_genome_id, family_id, capability, n_samples, mean_score, last_score, last_updated)
            VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(worker_genome_id, family_id, capability) DO UPDATE SET
            n_samples = n_samples + 1,
            mean_score = (mean_score * n_samples + ?) / (n_samples + 1),
            last_score = ?,
            last_updated = ?
        """, (worker_genome_id, family_id, capability, score, score, time.time(), score, score, time.time()))
        conn.commit()
        conn.close()

    def get_capabilities(self, worker_genome_id: str, family_id: str = "") -> list[dict]:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM capability_evidence WHERE worker_genome_id = ?"
        params = [worker_genome_id]
        if family_id:
            query += " AND family_id = ?"
            params.append(family_id)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ─── Failure Modes ────────────────────────────────────────────────

    def record_failure_mode(self, family_id: str, failure_mode: str,
                            severity: float, worker_id: str = ""):
        conn = self._conn()
        conn.execute("""
            INSERT INTO failure_modes (family_id, failure_mode, n_occurrences, severity, weakest_worker, last_updated)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(family_id, failure_mode) DO UPDATE SET
            n_occurrences = n_occurrences + 1,
            severity = ?,
            weakest_worker = ?,
            last_updated = ?
        """, (family_id, failure_mode, severity, worker_id, time.time(),
              severity, worker_id, time.time()))
        conn.commit()
        conn.close()

    # ─── Curriculum Archive ───────────────────────────────────────────

    def record_curriculum(self, family_id: str, niche_key: str,
                          world_genome_id: str, difficulty: int,
                          discriminative_power: float = 0,
                          worker_success_rate: float = 0):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO curriculum_archive
            (family_id, niche_key, world_genome_id, difficulty, discriminative_power,
             worker_success_rate, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (family_id, niche_key, world_genome_id, difficulty,
              discriminative_power, worker_success_rate, time.time()))
        conn.commit()
        conn.close()

    def get_curriculum(self, family_id: str, niche_key: str = "") -> list[dict]:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM curriculum_archive WHERE family_id = ?"
        params = [family_id]
        if niche_key:
            query += " AND niche_key = ?"
            params.append(niche_key)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ─── Experiments ──────────────────────────────────────────────────

    def record_experiment(self, experiment_id: str, hypothesis: str = "",
                          family_id: str = "", status: str = "running",
                          config: dict = None):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO experiments (experiment_id, hypothesis, family_id, status, config, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (experiment_id, hypothesis, family_id, status, json.dumps(config or {}), time.time()))
        conn.commit()
        conn.close()

    # ─── Insights ─────────────────────────────────────────────────────

    def add_insight(self, insight_id: str, title: str, body: str = "",
                    kind: str = "", experiment_id: str = "",
                    evidence_runs: int = 0, confidence: float = 0):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO insights
            (insight_id, experiment_id, kind, title, body, evidence_runs, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (insight_id, experiment_id, kind, title, body, evidence_runs, confidence, time.time()))
        conn.commit()
        conn.close()

    # ─── Graph ────────────────────────────────────────────────────────

    def add_node(self, node_id: str, label: str, properties: dict = None):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO graph_nodes (id, label, properties, created_at)
            VALUES (?, ?, ?, ?)
        """, (node_id, label, json.dumps(properties or {}), time.time()))
        conn.commit()
        conn.close()

    def add_edge(self, source_id: str, target_id: str, edge_type: str,
                 properties: dict = None):
        conn = self._conn()
        conn.execute("""
            INSERT INTO graph_edges (source_id, target_id, edge_type, properties, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (source_id, target_id, edge_type, json.dumps(properties or {}), time.time()))
        conn.commit()
        conn.close()

    def get_failure_modes(self, family_id: str, min_frequency: float = 0.0) -> list[dict]:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM failure_modes WHERE family_id = ? AND frequency >= ?"
        params = [family_id, min_frequency]
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ─── Summary ──────────────────────────────────────────────────────

    def summary(self) -> dict:
        conn = self._conn()
        runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        worlds = conn.execute("SELECT COUNT(*) FROM world_genomes").fetchone()[0]
        workers = conn.execute("SELECT COUNT(*) FROM worker_genomes").fetchone()[0]
        experiments = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
        insights = conn.execute("SELECT COUNT(*) FROM insights").fetchone()[0]
        forecasts = conn.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
        conn.close()
        return {
            "total_runs": runs,
            "total_worlds": worlds,
            "total_workers": workers,
            "total_experiments": experiments,
            "total_insights": insights,
            "total_forecasts": forecasts,
        }

    def family_stats(self, family_id: str) -> dict:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM runs WHERE family_id = ?", (family_id,)
        ).fetchall()
        conn.close()
        if not rows:
            return {"total_runs": 0, "mean_quality": 0, "total_worlds": 0, "top_failures": []}
        runs = [dict(r) for r in rows]
        qualities = [r["quality_score"] for r in runs]
        return {
            "total_runs": len(runs),
            "mean_quality": sum(qualities) / len(qualities) if qualities else 0,
            "total_worlds": len(set(r["world_genome_id"] for r in runs)),
            "top_failures": [],
        }
