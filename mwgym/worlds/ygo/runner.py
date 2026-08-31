"""YGO World Adapter — BATS-integrated genome strategies for YGO.

Every decision goes through BATS:
- should_escalate() → buy Expert Policy (synthetic x402)
- should_branch() → explore non-optimal action
- select_model() → choose action type based on budget/uncertainty

DecisionPoints are recorded with full context and written to LabProjection.
Genome thresholds map to BATS parameters.

Usage:
  python3 -m mwgym.worlds.ygo --games 10 --all
"""
from __future__ import annotations

import json
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from mwgym.core.worker_genome import WorkerGenome
from mwgym.core.decision_point import DecisionPoint
from mwgym.core.budget_ledger import BudgetLedger
from mwgym.worlds.ygo.env import YGOEnv, SHOP, OPPONENT_STRATEGIES
from mwgym.worlds.ygo.evaluator import evaluate_game

# Import BATS from WorkerKit
sys.path.insert(0, str(Path("/root/workerkit")))
from providers.bats import BATS, BudgetState
from providers.registry import ProviderRegistry


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
    # BATS integration
    uncertainty: float = 0.5
    bats_escalate: bool = False
    bats_branch: bool = False
    bats_budget_remaining: float = 0.0
    bought_expert: bool = False


class YGOStrategy:
    """BATS-integrated genome strategy for YGO.

    Uses BATS for:
    - should_escalate() → buy Expert Policy when quality is low
    - should_branch() → explore when budget allows
    - Budget tracking via BudgetState
    """

    def __init__(self, genome: WorkerGenome, rng: random.Random = None,
                 lab_context: dict = None):
        self.genome = genome
        self.rng = rng or random.Random(42)
        self.decisions: list[YGOTurnDecision] = []
        self.ledger = BudgetLedger(daily_cap=100.0, per_run_cap=50.0)

        # BATS integration
        self._registry = ProviderRegistry()
        self._bats = BATS(self._registry)
        self._budget = BudgetState(
            total_usd=50.0, remaining_usd=50.0,
            max_model_calls=20, max_wall_seconds=300,
        )

        # Lab context (Hydra prior)
        self._lab_context = lab_context or {}
        self._prior_win_rate = self._lab_context.get("win_rate", 0.5)
        self._prior_avg_reward = self._lab_context.get("avg_reward", 5.0)

        # Track state for BATS
        self._consecutive_losses = 0
        self._consecutive_wins = 0
        self._total_reward = 0.0

    def _estimate_uncertainty(self, env: YGOEnv) -> float:
        """Estimate uncertainty based on game state and history.

        High uncertainty = need more computation / expert help.
        Low uncertainty = can act greedily.
        """
        state = env.state

        # Factors that increase uncertainty:
        # 1. Low HP → high stakes → need expert
        hp_ratio = state.player_hp / 8000
        hp_uncertainty = max(0, 1.0 - hp_ratio) * 0.3

        # 2. Opponent has strong field → need to think harder
        opp_threat = sum(c["attack"] for c in state.opponent_field) / 10000
        threat_uncertainty = opp_threat * 0.2

        # 3. Many options available → branching uncertainty
        n_options = len(env.available_actions())
        option_uncertainty = min(n_options / 10, 0.2)

        # 4. Recent performance → if losing, uncertainty increases
        perf_uncertainty = 0.0
        if self._consecutive_losses > 2:
            perf_uncertainty = 0.2
        elif self._consecutive_wins > 3:
            perf_uncertainty = -0.1  # confident

        # 5. Credits available → more credits = more options = more uncertainty
        credit_ratio = state.player_credits / 30
        credit_uncertainty = credit_ratio * 0.1

        uncertainty = 0.2 + hp_uncertainty + threat_uncertainty + option_uncertainty + perf_uncertainty + credit_uncertainty
        return max(0.0, min(1.0, uncertainty))

    def _should_buy_expert(self, env: YGOEnv) -> bool:
        """Use BATS to decide whether to buy Expert Policy.

        Expert Policy costs 20 credits and reveals optimal play.
        Only worth it when uncertainty is high and budget allows.
        """
        uncertainty = self._estimate_uncertainty(env)

        # Check if we can afford it
        expert_cost = 20
        if env.state.player_credits < expert_cost:
            return False

        # Use BATS to decide
        should = self._bats.should_escalate(
            current_model="local",
            quality_score=1.0 - uncertainty,  # low quality = high uncertainty
            budget=self._budget,
        )

        # Also check genome threshold
        if uncertainty > self.genome.escalate_model_threshold:
            should = True

        return should

    def _should_explore(self, env: YGOEnv) -> bool:
        """Use BATS to decide whether to explore non-optimal action.

        Exploration is valuable when:
        - Budget allows (should_branch)
        - Genome has exploration_rate > 0
        - We haven't explored much yet
        """
        if self.genome.exploration_rate <= 0:
            return False

        should = self._bats.should_branch(
            budget=self._budget,
            n_candidates=self._consecutive_losses,
        )

        # Blend BATS decision with genome exploration rate
        if should and self.rng.random() < self.genome.exploration_rate:
            return True

        return False

    def choose_action(self, env: YGOEnv) -> dict:
        actions = env.available_actions()
        if not actions:
            return {"type": "end_turn"}

        state = env.state
        uncertainty = self._estimate_uncertainty(env)

        # BATS decisions
        buy_expert = self._should_buy_expert(env)
        explore = self._should_explore(env)

        # Update budget
        self._budget.record_spend(0.0, tokens=0)

        decision = YGOTurnDecision(
            turn=state.turn,
            credits_available=state.player_credits,
            options_count=len(actions),
            uncertainty=uncertainty,
            bats_escalate=buy_expert,
            bats_branch=explore,
            bats_budget_remaining=self._budget.remaining_usd,
        )

        # If BATS says buy expert, buy it
        if buy_expert:
            expert_item = next((i for i in SHOP if i["effect"] == "optimal_play_recommended"), None)
            if expert_item:
                for action in actions:
                    if action["type"] == "buy" and action.get("item", {}).get("id") == expert_item["id"]:
                        decision.selected_action = action
                        decision.predicted_value = 0.9  # expert is high value
                        decision.bought_expert = True
                        self.decisions.append(decision)
                        return action

        # Score actions
        scored = []
        for action in actions:
            score = self._score_action(action, env, uncertainty)
            scored.append((score, action))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Exploration: pick non-optimal
        if explore and len(scored) > 1:
            selected = scored[1][1]
        else:
            selected = scored[0][1]

        decision.selected_action = selected
        decision.predicted_value = selected.get("estimated_value", 0)
        decision.alternatives_considered = len(scored) - 1

        self.decisions.append(decision)
        return selected

    def _score_action(self, action: dict, env: YGOEnv, uncertainty: float) -> float:
        """Score action using BATS-informed logic + genome thresholds."""
        base = action.get("estimated_value", 0)
        cost = action.get("cost", 0)

        # Cost penalty (genome-dependent)
        if cost > 0:
            cost_penalty = cost / max(1, env.state.player_credits) * (1 - self.genome.self_build_threshold)
            base -= cost_penalty

        # Type bonuses (BATS-informed)
        if action["type"] == "attack":
            # Attack value increases with uncertainty (need to end game fast)
            attack_bonus = 0.3 * (1 - self.genome.escalate_model_threshold)
            attack_bonus *= (1 + uncertainty * 0.5)  # more valuable when uncertain
            base += attack_bonus

        elif action["type"] == "buy":
            item = action.get("item", {})
            if item.get("effect") == "optimal_play_recommended":
                # Expert policy: only valuable when uncertainty is HIGH
                if uncertainty > self.genome.escalate_model_threshold:
                    base += 0.8  # high value when uncertain
                else:
                    base -= 0.3  # wasteful when confident
            elif item.get("effect") == "double_attack_next":
                # Power boost: valuable when we have field advantage
                if env.state.player_field and not env.state.opponent_field:
                    base += 0.4  # direct attack boost
                else:
                    base *= 0.5
            elif item.get("effect") == "negate_next_attack":
                # Shield: valuable when opponent has strong field
                opp_threat = sum(c["attack"] for c in env.state.opponent_field) / 10000
                base += opp_threat * 0.6
            else:
                base *= self.genome.buy_threshold

        elif action["type"] == "play_card":
            card = action.get("card", {})
            efficiency = card.get("attack", 0) / max(1, card.get("cost", 1))
            base += efficiency * 0.1

            # High-value cards are more important when uncertain
            if card.get("attack", 0) > 2000:
                base += uncertainty * 0.2

        return base

    def record_outcome(self, reward: float):
        if self.decisions:
            self.decisions[-1].actual_reward = reward

        self._total_reward += reward
        if reward > 0:
            self._consecutive_wins += 1
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1
            self._consecutive_wins = 0

    def get_decision_points(self) -> list[dict]:
        """Convert decisions to DecisionPoint format for LabProjection."""
        points = []
        for d in self.decisions:
            dp = DecisionPoint(
                id=f"dp-{d.turn}-{id(d)}",
                run_id=f"ygo-{d.turn}",
                task_family="ygo.battle",
                context_features={
                    "credits": d.credits_available,
                    "turn": d.turn,
                    "options": d.options_count,
                    "uncertainty": d.uncertainty,
                    "bats_escalate": float(d.bats_escalate),
                    "bats_branch": float(d.bats_branch),
                    "bats_budget": d.bats_budget_remaining,
                },
                options=[{
                    "type": d.selected_action.get("type", "?"),
                    "value": d.predicted_value,
                    "bought_expert": d.bought_expert,
                }],
                selected_option_id=d.selected_action.get("type", "?"),
                predicted_quality=d.predicted_value,
                actual_success=d.actual_reward > 0,
            )
            dp.record_outcome(cost=0, quality=d.actual_reward, success=d.actual_reward > 0)
            points.append(dp.to_dict())
        return points

    def summary(self) -> dict:
        total_reward = sum(d.actual_reward for d in self.decisions)
        good_decisions = sum(1 for d in self.decisions if d.actual_reward > 0)
        expert_buys = sum(1 for d in self.decisions if d.bought_expert)
        bats_escalations = sum(1 for d in self.decisions if d.bats_escalate)
        bats_explorations = sum(1 for d in self.decisions if d.bats_branch)
        avg_uncertainty = sum(d.uncertainty for d in self.decisions) / max(1, len(self.decisions))

        return {
            "genome_id": self.genome.id,
            "total_reward": round(total_reward, 3),
            "decisions": len(self.decisions),
            "good_decisions": good_decisions,
            "decision_quality": round(good_decisions / max(1, len(self.decisions)), 3),
            "avg_alternatives": round(
                sum(d.alternatives_considered for d in self.decisions) / max(1, len(self.decisions)), 1),
            # BATS metrics
            "avg_uncertainty": round(avg_uncertainty, 3),
            "bats_escalations": bats_escalations,
            "bats_explorations": bats_explorations,
            "expert_buys": expert_buys,
            "budget_remaining": round(self._budget.remaining_usd, 4),
        }


class YGORunner:
    """Run YGO games with BATS-integrated genome strategies."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.results: list[dict] = []

    def run_game(self, genome: WorkerGenome, game_seed: int,
                 opponent: str = "passive", lab_context: dict = None) -> dict:
        env = YGOEnv(seed=game_seed, opponent=opponent)
        strategy = YGOStrategy(genome, rng=random.Random(game_seed),
                               lab_context=lab_context)

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
        decision_points = strategy.get_decision_points()

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
                # Get lab context for this genome (Hydra prior)
                lab_context = self._get_lab_context(genome_id, opponent)

                for i in range(n_games):
                    game_seed = self.seed + i
                    result = self.run_game(genome, game_seed, opponent, lab_context)
                    results.append(result)
                    print(f"  {genome_id} vs {opponent} game-{i}: "
                          f"won={result['game_eval']['won']} "
                          f"reward={result['game_eval']['total_reward']} "
                          f"uncertainty={result['strategy']['avg_uncertainty']:.2f} "
                          f"escalations={result['strategy']['bats_escalations']} "
                          f"expert_buys={result['strategy']['expert_buys']}")

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
                    "avg_uncertainty": round(
                        sum(r["strategy"]["avg_uncertainty"] for r in gr) / len(gr), 3),
                    "total_bats_escalations": sum(r["strategy"]["bats_escalations"] for r in gr),
                    "total_bats_explorations": sum(r["strategy"]["bats_explorations"] for r in gr),
                    "total_expert_buys": sum(r["strategy"]["expert_buys"] for r in gr),
                }

        # Log
        run_id = f"ygo-{int(time.time())}"
        log_dir = Path("/root/mwgym/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_data = {
            "run_id": run_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "experiment": "ygo-bats-integrated",
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

    def _get_lab_context(self, genome_id: str, opponent: str) -> dict:
        """Query LabProjection for past performance (Hydra prior)."""
        try:
            sys.path.insert(0, str(Path("/root/mwgym")))
            from mwgym.lab_bridge import LabBridge
            bridge = LabBridge()

            # Query past win rate for this genome
            agent_id = f"mwgym-ygo-{genome_id}"
            win_rate = bridge.win_rate(agent_id)

            # Query past runs
            runs = bridge.query_runs(agent_id=agent_id, limit=50)
            avg_reward = 0
            if runs:
                avg_reward = sum(r.get("reward_usd", 0) for r in runs) / len(runs)

            return {
                "win_rate": win_rate,
                "avg_reward": avg_reward,
                "n_past_runs": len(runs),
            }
        except Exception:
            return {"win_rate": 0.5, "avg_reward": 5.0, "n_past_runs": 0}
