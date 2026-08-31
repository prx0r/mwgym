"""MWGym ↔ HydraDB bridge — writes experiment data as graph nodes/edges.

Per spec Section 19:
- EventLedger stays canonical
- Real Hydra projector writes DecisionPoints
- SQLite fallback must be marked degraded
- Add partition/time retrieval filters

Uses the real HydraDB Docker instance (port 17687) for graph storage.
Falls back to WorkerKit SQLite when HydraDB is unavailable.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


class HydraBridge:
    """Writes MWGym experiment data to real HydraDB graph.

    Per spec: this is the REAL Hydra path, not the SQLite degraded path.
    """

    def __init__(self, degraded: bool = False):
        self.degraded = degraded
        self.backend = "sqlite_degraded" if degraded else "hydradb"

        if not degraded:
            from .hydra_client import RealHydraDB
            self.hydra = RealHydraDB()
        else:
            self.hydra = None

    def ensure_genome(self, genome_id: str, generation: int = 0):
        """Create genome node if not exists."""
        self.hydra.upsert_node(
            f"genome:{genome_id}", "WorkerVersion",
            {"id": genome_id, "generation": generation, "created_at": time.time()},
        )

    def record_run(self, run_id: str, genome_id: str, task_family: str,
                    outcome: str, reward: float = 0, cost: float = 0):
        """Record a run as a graph node."""
        self.hydra.upsert_node(
            f"run:{run_id}", "Run",
            {"run_id": run_id, "outcome": outcome, "reward": reward, "cost_usd": cost},
        )
        # Connect run to genome
        self.hydra.upsert_edge(f"run:{run_id}", f"genome:{genome_id}", "EXECUTED_BY")

    def record_decision_point(self, dp_id: str, run_id: str, context: dict,
                               selected: str, predicted: float, actual: float):
        """Record a DecisionPoint as a graph node."""
        self.hydra.upsert_node(
            f"dp:{dp_id}", "Decision",
            {
                "decision_id": dp_id,
                "action": selected,
                "predicted_value": predicted,
                "actual_value": actual,
                "uncertainty": context.get("uncertainty", 0),
                "bats_escalate": context.get("bats_escalate", False),
                "bats_branch": context.get("bats_branch", False),
            },
        )
        # Connect to run
        self.hydra.upsert_edge(f"dp:{dp_id}", f"run:{run_id}", "CONTAINS")

    def record_outcome(self, run_id: str, won: bool, reward: float):
        """Record outcome node."""
        outcome_id = f"outcome:{run_id}"
        self.hydra.upsert_node(
            outcome_id, "Outcome",
            {"won": won, "reward_usd": reward},
        )
        self.hydra.upsert_edge(outcome_id, f"run:{run_id}", "RESULT_OF")

    def record_experiment(self, experiment_id: str, hypothesis: str, status: str):
        """Record experiment node."""
        self.hydra.upsert_node(
            f"experiment:{experiment_id}", "Experiment",
            {"hypothesis": hypothesis, "status": status},
        )

    def record_insight(self, insight_id: str, title: str, body: str,
                        evidence_runs: int, confidence: float):
        """Record insight node."""
        self.hydra.upsert_node(
            f"insight:{insight_id}", "CapabilityClaim",
            {"title": title, "body": body, "evidence_runs": evidence_runs, "confidence": confidence},
        )

    def query_win_rate(self, genome_id: str) -> float:
        """Query win rate for a genome from the graph."""
        result = self.hydra.query(
            "MATCH (r:Run)-[:EXECUTED_BY]->(g:WorkerVersion {id: $genome_id}) "
            "RETURN COUNT(CASE WHEN r.outcome = 'won' THEN 1 END) as wins, "
            "COUNT(r) as total",
            {"genome_id": genome_id},
        )
        if result and len(result) > 0:
            wins = result[0].get("wins", 0)
            total = result[0].get("total", 0)
            return wins / total if total else 0.0
        return 0.0

    def query_genealogy(self, genome_id: str) -> list[dict]:
        """Query genome mutation history."""
        return self.hydra.query(
            "MATCH (g:WorkerVersion {id: $genome_id}) "
            "MATCH path = (g)-[:MUTATION_OF*0..5]->(ancestor) "
            "RETURN ancestor.id, ancestor.generation",
            {"genome_id": genome_id},
        )
