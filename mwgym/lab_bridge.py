"""LabBridge — writes MWGym experiment results to WorkerKit's LabProjection.

This is the missing connection between MWGym experiments and the shared
empirical memory. Every experiment run, genome performance, and outcome
gets written to the same SQLite db that WorkerKit uses for queries.

Usage:
  from mwgym.lab_bridge import LabBridge
  bridge = LabBridge()
  bridge.record_crossover_run(run_id, genome, task, success, tokens, ms)
  bridge.record_ygo_run(run_id, genome, opponent, won, reward)
  summary = bridge.lab_summary()
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Import WorkerKit's LabProjection directly
sys.path.insert(0, str(Path("/root/workerkit")))
from hydra.store import LabProjection


WORKERKIT_DB = "/root/workerkit/data/hydra.db"


class LabBridge:
    """Writes MWGym experiment data to WorkerKit's LabProjection."""

    def __init__(self, db_path: str = WORKERKIT_DB):
        self.lab = LabProjection(db_path=db_path, append_only=False)

    def ensure_agent(self, agent_id: str, template: str = "mwgym"):
        """Ensure an agent exists in the lab."""
        existing = self.lab.get_agent(agent_id)
        if not existing:
            self.lab.upsert_agent(agent_id, template, lab_id="mwgym")

    def record_experiment(self, experiment_id: str, hypothesis: str,
                          status: str = "running", data: dict = None):
        """Record an experiment."""
        try:
            self.lab.record_experiment(
                experiment_id=experiment_id,
                hypothesis=hypothesis,
                status=status,
                data=data or {},
            )
        except ValueError:
            pass  # append-only, already exists

    def record_crossover_run(self, run_id: str, genome: str, task_id: str,
                              success: bool, tokens: int, duration_ms: int,
                              cost_usd: float = 0.0, artifacts: list = None,
                              experiment_id: str = ""):
        """Record a single crossover experiment run."""
        agent_id = f"mwgym-{genome}"
        self.ensure_agent(agent_id, template=f"crossover-{genome}")

        outcome = "won" if success else "lost"
        task_family = "crossover.filesystem"

        # Use unique run_id to avoid append-only conflicts
        unique_run_id = f"{experiment_id}-{genome}-{task_id}"

        self.lab.record_run(
            run_id=unique_run_id,
            agent_id=agent_id,
            opportunity_id=experiment_id,
            task_family=task_family,
            model="mimo-v2.5",
            cost_usd=cost_usd,
            duration_s=duration_ms / 1000,
            evaluation_score=1.0 if success else 0.0,
            outcome=outcome,
            reward_usd=0.0,
            worker_version=genome,
        )

        # Record dependencies
        self.lab.record_run_dependency(
            run_id=unique_run_id,
            worker_version_id=genome,
        )

    def record_ygo_run(self, run_id: str, genome: str, opponent: str,
                        won: bool, reward: float, turns: int,
                        decision_quality: float, experiment_id: str = ""):
        """Record a single YGO game run."""
        agent_id = f"mwgym-ygo-{genome}"
        self.ensure_agent(agent_id, template=f"ygo-{genome}")

        outcome = "won" if won else "lost"
        task_family = f"ygo.battle.{opponent}"

        # Use unique run_id
        unique_run_id = f"{experiment_id}-{genome}-{opponent}-{run_id.split('-')[-1]}"

        self.lab.record_run(
            run_id=unique_run_id,
            agent_id=agent_id,
            opportunity_id=experiment_id,
            task_family=task_family,
            model="local",
            cost_usd=0.0,
            duration_s=turns,
            evaluation_score=decision_quality,
            outcome=outcome,
            reward_usd=reward,
            worker_version=genome,
        )

    def record_crossover_experiment(self, experiment_id: str, results: list[dict],
                                      genomes: list[str]):
        """Record a full crossover experiment and its results."""
        # Count outcomes per genome
        genome_stats = {}
        for r in results:
            g = r.get("genome", "unknown")
            if g not in genome_stats:
                genome_stats[g] = {"won": 0, "lost": 0, "total_tokens": 0, "total_ms": 0}
            if r.get("success", False):
                genome_stats[g]["won"] += 1
            else:
                genome_stats[g]["lost"] += 1
            genome_stats[g]["total_tokens"] += r.get("tokens", 0)
            genome_stats[g]["total_ms"] += r.get("ms", 0)

        # Record the experiment
        self.record_experiment(
            experiment_id=experiment_id,
            hypothesis=f"Comparing {', '.join(genomes)} on filesystem tasks",
            status="completed",
            data={"genomes": genomes, "genome_stats": genome_stats},
        )

        # Record each run
        for r in results:
            self.record_crossover_run(
                run_id=f"{experiment_id}-{r.get('task_id', 'unknown')}",
                genome=r.get("genome", "unknown"),
                task_id=r.get("task_id", "unknown"),
                success=r.get("success", False),
                tokens=r.get("tokens", 0),
                duration_ms=r.get("ms", 0),
                experiment_id=experiment_id,
            )

        # Record insights
        for genome, stats in genome_stats.items():
            total = stats["won"] + stats["lost"]
            win_rate = stats["won"] / total if total else 0
            self.lab.add_insight(
                insight_id=f"insight-{experiment_id}-{genome}",
                title=f"{genome} win rate: {win_rate*100:.0f}%",
                body=f"Genome {genome} won {stats['won']}/{total} tasks. "
                     f"Avg tokens: {stats['total_tokens']/max(1,total):.0f}. "
                     f"Avg latency: {stats['total_ms']/max(1,total):.0f}ms.",
                evidence_runs=total,
                confidence=win_rate,
            )

    def record_ygo_experiment(self, experiment_id: str, results: list[dict],
                                genome_ids: list[str], opponents: list[str]):
        """Record a full YGO experiment and its results."""
        # Count outcomes per genome×opponent
        matrix = {}
        for r in results:
            g = r.get("genome", "unknown")
            o = r.get("opponent", "unknown")
            key = f"{g}_vs_{o}"
            if key not in matrix:
                matrix[key] = {"won": 0, "lost": 0, "rewards": []}
            if r.get("game_eval", {}).get("won", False):
                matrix[key]["won"] += 1
            else:
                matrix[key]["lost"] += 1
            matrix[key]["rewards"].append(r.get("game_eval", {}).get("total_reward", 0))

        # Record experiment
        self.record_experiment(
            experiment_id=experiment_id,
            hypothesis=f"YGO genome allocation: {', '.join(genome_ids)} vs {', '.join(opponents)}",
            status="completed",
            data={"genomes": genome_ids, "opponents": opponents, "matrix": matrix},
        )

        # Record each game + DecisionPoints
        for r in results:
            game_eval = r.get("game_eval", {})
            strategy = r.get("strategy", {})
            run_id = f"{experiment_id}-{r.get('game_seed', 'unknown')}"

            self.record_ygo_run(
                run_id=run_id,
                genome=r.get("genome", "unknown"),
                opponent=r.get("opponent", "unknown"),
                won=game_eval.get("won", False),
                reward=game_eval.get("total_reward", 0),
                turns=game_eval.get("turns", 0),
                decision_quality=strategy.get("decision_quality", 0),
                experiment_id=experiment_id,
            )

            # Record DecisionPoints
            for dp in r.get("decision_points", []):
                self.record_decision_point(dp, run_id)

        # Record insights per genome
        for genome in genome_ids:
            wins = sum(1 for r in results if r.get("genome") == genome and r.get("game_eval", {}).get("won"))
            total = sum(1 for r in results if r.get("genome") == genome)
            win_rate = wins / total if total else 0
            avg_reward = sum(r.get("game_eval", {}).get("total_reward", 0)
                           for r in results if r.get("genome") == genome) / max(1, total)

            # BATS metrics
            total_escalations = sum(r.get("strategy", {}).get("bats_escalations", 0)
                                   for r in results if r.get("genome") == genome)
            total_explorations = sum(r.get("strategy", {}).get("bats_explorations", 0)
                                    for r in results if r.get("genome") == genome)
            total_expert_buys = sum(r.get("strategy", {}).get("expert_buys", 0)
                                   for r in results if r.get("genome") == genome)
            avg_uncertainty = sum(r.get("strategy", {}).get("avg_uncertainty", 0)
                                for r in results if r.get("genome") == genome) / max(1, total)

            self.lab.add_insight(
                insight_id=f"insight-{experiment_id}-{genome}",
                title=f"YGO {genome}: {win_rate*100:.0f}% win rate",
                body=f"Genome {genome} won {wins}/{total} games. "
                     f"Avg reward: {avg_reward:.1f}. "
                     f"BATS escalations: {total_escalations}, explorations: {total_explorations}, "
                     f"expert buys: {total_expert_buys}. Avg uncertainty: {avg_uncertainty:.2f}.",
                evidence_runs=total,
                confidence=win_rate,
            )

    def record_decision_point(self, dp: dict, run_id: str):
        """Record a DecisionPoint to LabProjection."""
        # Store as an insight with the decision context
        dp_id = dp.get("id", f"dp-{int(time.time()*1000)}")
        context = dp.get("context_features", {})
        selected = dp.get("selected_option_id", "?")

        self.lab.add_insight(
            insight_id=f"dp-{run_id}-{dp_id}",
            title=f"Decision: {selected} (turn={context.get('turn', '?')})",
            body=f"Context: credits={context.get('credits', '?')}, "
                 f"uncertainty={context.get('uncertainty', '?')}, "
                 f"options={context.get('options', '?')}. "
                 f"Selected: {selected}. "
                 f"BATS escalate={context.get('bats_escalate', '?')}, "
                 f"branch={context.get('bats_branch', '?')}.",
            evidence_runs=1,
            confidence=dp.get("predicted_quality", 0.5),
        )

    def summary(self) -> dict:
        """Get lab summary from WorkerKit's LabProjection."""
        return self.lab.lab_summary()

    def win_rate(self, agent_id: str = "") -> float:
        return self.lab.win_rate(agent_id)

    def profitability_by_model(self) -> list[dict]:
        return self.lab.profitability_by_model()

    def query_runs(self, **kwargs) -> list[dict]:
        return self.lab.get_runs(**kwargs)
