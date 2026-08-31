"""YGO World Adapter — connects YGO environment to MWGym genome evolution.

Runs YGO games using different WorkerGenome configurations against varied
opponent strategies. Measures which resource allocation strategies win.

Usage:
  python3 -m mwgym.worlds.ygo.runner --games 10 --opponents passive,aggressive
  python3 -m mwgym.worlds.ygo.runner --games 5 --all
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from mwgym.core.worker_genome import WorkerGenome
from mwgym.core.decision_point import DecisionPoint
from mwgym.core.budget_ledger import BudgetLedger
from mwgym.worlds.ygo.env import YGOEnv, SHOP, OPPONENT_STRATEGIES
from mwgym.worlds.ygo.evaluator import evaluate_game


# Predefined genome strategies for YGO
YGO_GENOMES = {
    "static": WorkerGenome.static(),
    "memory": WorkerGenome.memory(),
    "memory_bats": WorkerGenome.memory_bats(),
}


@dataclass
class YGOTurnDecision:
    turn: int
    credits_available: int
    options_count: int
    selected_action: dict = field(default_factory=dict)
    predicted_value: float = 0.0
    actual_reward: float = 0.0
    alternatives_considered: int = 0


class YGOStrategy:
    """Genome-driven strategy for YGO."""

    def __init__(self, genome: WorkerGenome, rng: random.Random = None):
        self.genome = genome
        self.rng = rng or random.Random(42)
        self.decisions: list[YGOTurnDecision] = []
        self.ledger = BudgetLedger(daily_cap=100.0, per_run_cap=50.0)

    def choose_action(self, env: YGOEnv) -> dict:
        actions = env.available_actions()
        if not actions:
            return {"type": "end_turn"}

        state = env.state
        decision = YGOTurnDecision(
            turn=state.turn,
            credits_available=state.player_credits,
            options_count=len(actions),
        )

        scored = []
        for action in actions:
            score = self._score_action(action, env)
            scored.append((score, action))

        scored.sort(key=lambda x: x[0], reverse=True)

        if (self.genome.exploration_rate > 0 and
                len(scored) > 1 and
                self.rng.random() < self.genome.exploration_rate):
            selected = scored[1][1]
        else:
            selected = scored[0][1]

        decision.selected_action = selected
        decision.predicted_value = selected.get("estimated_value", 0)
        decision.alternatives_considered = len(scored) - 1

        self.decisions.append(decision)
        return selected

    def _score_action(self, action: dict, env: YGOEnv) -> float:
        base = action.get("estimated_value", 0)
        cost = action.get("cost", 0)
        if cost > 0:
            cost_penalty = cost / max(1, env.state.player_credits) * (1 - self.genome.self_build_threshold)
            base -= cost_penalty

        if action["type"] == "attack":
            base += 0.3 * (1 - self.genome.escalate_model_threshold)
        elif action["type"] == "buy":
            item = action.get("item", {})
            if item.get("effect") == "optimal_play_recommended":
                base += 0.5 * self.genome.escalate_model_threshold
            else:
                base *= self.genome.buy_threshold
        elif action["type"] == "play_card":
            card = action.get("card", {})
            efficiency = card.get("attack", 0) / max(1, card.get("cost", 1))
            base += efficiency * 0.1

        return base

    def record_outcome(self, reward: float):
        if self.decisions:
            self.decisions[-1].actual_reward = reward

    def summary(self) -> dict:
        total_reward = sum(d.actual_reward for d in self.decisions)
        good_decisions = sum(1 for d in self.decisions if d.actual_reward > 0)
        return {
            "genome_id": self.genome.id,
            "total_reward": round(total_reward, 3),
            "decisions": len(self.decisions),
            "good_decisions": good_decisions,
            "decision_quality": round(good_decisions / max(1, len(self.decisions)), 3),
            "avg_alternatives": round(
                sum(d.alternatives_considered for d in self.decisions) / max(1, len(self.decisions)), 1),
        }


class YGORunner:
    """Run YGO games with different genome strategies and opponents."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.results: list[dict] = []

    def run_game(self, genome: WorkerGenome, game_seed: int, opponent: str = "passive") -> dict:
        env = YGOEnv(seed=game_seed, opponent=opponent)
        strategy = YGOStrategy(genome, rng=random.Random(game_seed))

        obs = env.reset()
        done = False
        total_reward = 0.0

        while not done:
            action = strategy.choose_action(env)
            obs, reward, done, info = env.step(action)
            total_reward += reward
            strategy.record_outcome(reward)

        game_eval = evaluate_game(env.history, obs)
        strat_summary = strategy.summary()

        decision_points = []
        for d in strategy.decisions:
            dp = DecisionPoint(
                id=f"dp-{game_seed}-{d.turn}",
                run_id=f"ygo-{game_seed}",
                task_family="ygo.battle",
                context_features={
                    "credits": d.credits_available,
                    "turn": d.turn,
                    "options": d.options_count,
                },
                options=[{"type": d.selected_action.get("type", "?"), "value": d.predicted_value}],
                selected_option_id=d.selected_action.get("type", "?"),
                predicted_quality=d.predicted_value,
                actual_success=d.actual_reward > 0,
            )
            dp.record_outcome(cost=0, quality=d.actual_reward, success=d.actual_reward > 0)
            decision_points.append(dp.to_dict())

        return {
            "genome": genome.id,
            "opponent": opponent,
            "game_seed": game_seed,
            "game_eval": game_eval,
            "strategy": strat_summary,
            "decision_points": decision_points,
            "history_length": len(env.history),
        }

    def run_experiment(self, n_games: int = 10,
                       genome_ids: list[str] = None,
                       opponents: list[str] = None) -> dict:
        if genome_ids is None:
            genome_ids = ["static", "memory", "memory_bats"]
        if opponents is None:
            opponents = ["passive"]

        genomes = {k: v for k, v in YGO_GENOMES.items() if k in genome_ids}
        results = []

        for genome_id, genome in genomes.items():
            for opponent in opponents:
                for i in range(n_games):
                    game_seed = self.seed + i
                    result = self.run_game(genome, game_seed, opponent)
                    results.append(result)
                    print(f"  {genome_id} vs {opponent} game-{i}: "
                          f"won={result['game_eval']['won']} "
                          f"reward={result['game_eval']['total_reward']}")

        self.results = results

        # Aggregate per genome × opponent
        summary = {}
        for genome_id in genomes:
            for opponent in opponents:
                key = f"{genome_id}_vs_{opponent}"
                gr = [r for r in results if r["genome"] == genome_id and r["opponent"] == opponent]
                if not gr:
                    continue
                wins = sum(1 for r in gr if r["game_eval"]["won"])
                summary[key] = {
                    "genome": genome_id,
                    "opponent": opponent,
                    "n": len(gr),
                    "wins": wins,
                    "win_rate": round(wins / len(gr), 3),
                    "avg_reward": round(sum(r["game_eval"]["total_reward"] for r in gr) / len(gr), 3),
                    "avg_efficiency": round(sum(r["game_eval"]["efficiency"] for r in gr) / len(gr), 3),
                    "avg_decision_quality": round(
                        sum(r["strategy"]["decision_quality"] for r in gr) / len(gr), 3),
                }

        # Log
        run_id = f"ygo-{int(time.time())}"
        log_dir = Path("/root/mwgym/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_data = {
            "run_id": run_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "experiment": "ygo-genome-opponent-matrix",
            "n_games": n_games,
            "genome_ids": genome_ids,
            "opponents": opponents,
            "results": results,
            "summary": summary,
        }
        log_path = log_dir / f"{run_id}.json"
        log_path.write_text(json.dumps(log_data, indent=2))
        print(f"\nLog: {log_path}")

        return {"summary": summary, "log": str(log_path)}
