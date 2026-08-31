"""YGO-003: Resource Allocation Experiment

Per spec Section 47:
Arms: uniform, fixed threshold, budget tracker, threshold budget router, BATS, shadow-price, Thompson, empirical oracle
Budgets: LOW, MEDIUM, HIGH
Primary plots: win rate vs compute, utility vs compute, allocation regret vs budget
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mwgym.worlds.ygo.adapter import make
from mwgym.decision_features import DecisionFeatureExtractor
from mwgym.meta_actions import MetaAction, MetaActionExecutor, META_ACTION_COSTS
from mwgym.telemetry_records import TelemetryStore, ResourceSpend
from mwgym.asset_profile import AssetProfile, AssetProfileStore
from mwgym.stack_oracle import StackOracle


class Allocator:
    """Base allocator class."""

    def __init__(self, name: str):
        self.name = name

    def decide(self, features: dict, executor: MetaActionExecutor) -> MetaAction:
        """Decide which meta-action to take."""
        return MetaAction.ACT_NOW


class UniformAllocator(Allocator):
    """A0: Always ACT_NOW."""

    def __init__(self):
        super().__init__("A0-uniform")

    def decide(self, features: dict, executor: MetaActionExecutor) -> MetaAction:
        return MetaAction.ACT_NOW


class FixedThresholdAllocator(Allocator):
    """A1: Fixed threshold — escalate if uncertainty > 0.7."""

    def __init__(self):
        super().__init__("A1-fixed-threshold")

    def decide(self, features: dict, executor: MetaActionExecutor) -> MetaAction:
        if features.get("estimated_uncertainty", 0) > 0.7:
            if executor.can_afford(MetaAction.ROLLOUT_4):
                return MetaAction.ROLLOUT_4
        return MetaAction.ACT_NOW


class BudgetTrackerAllocator(Allocator):
    """A2: Budget tracker — spend budget proportionally."""

    def __init__(self):
        super().__init__("A2-budget-tracker")

    def decide(self, features: dict, executor: MetaActionExecutor) -> MetaAction:
        fraction = executor.remaining_budget / max(1, executor.total_budget)
        if fraction > 0.5 and executor.can_afford(MetaAction.ROLLOUT_4):
            return MetaAction.ROLLOUT_4
        elif fraction > 0.2 and executor.can_afford(MetaAction.CHEAP_MODEL):
            return MetaAction.CHEAP_MODEL
        return MetaAction.ACT_NOW


class ThresholdBudgetAllocator(Allocator):
    """A3: Threshold budget — uncertainty + budget aware."""

    def __init__(self):
        super().__init__("A3-threshold-budget")

    def decide(self, features: dict, executor: MetaActionExecutor) -> MetaAction:
        uncertainty = features.get("estimated_uncertainty", 0)
        budget_frac = executor.remaining_budget / max(1, executor.total_budget)

        if uncertainty > 0.7 and budget_frac > 0.3:
            if executor.can_afford(MetaAction.ROLLOUT_16):
                return MetaAction.ROLLOUT_16
        elif uncertainty > 0.5 and budget_frac > 0.2:
            if executor.can_afford(MetaAction.ROLLOUT_4):
                return MetaAction.ROLLOUT_4
        elif uncertainty > 0.3 and budget_frac > 0.1:
            if executor.can_afford(MetaAction.CHEAP_MODEL):
                return MetaAction.CHEAP_MODEL
        return MetaAction.ACT_NOW


class ThompsonAllocator(Allocator):
    """A7: Thompson sampling — sample from asset posteriors."""

    def __init__(self):
        super().__init__("A7-thompson")
        self.profiles = AssetProfileStore('/tmp/ygo-003-thompson.json')
        self.rng = random.Random()

    def decide(self, features: dict, executor: MetaActionExecutor) -> MetaAction:
        # Sample from posteriors for each meta-action
        best_action = MetaAction.ACT_NOW
        best_utility = -1

        for action in MetaAction:
            if not executor.can_afford(action):
                continue
            profile = self.profiles.get(f"action-{action.value}")
            p_success = profile.sample_success(rng=self.rng)
            cost = META_ACTION_COSTS[action].credits
            utility = p_success * 10 - cost  # simplified utility
            if utility > best_utility:
                best_utility = utility
                best_action = action

        return best_action

    def record_outcome(self, action: MetaAction, success: bool):
        self.profiles.update(f"action-{action.value}", success=success)


class EmpiricalOracle(Allocator):
    """A8: Empirical oracle — best observed allocation (upper bound)."""

    def __init__(self):
        super().__init__("A8-empirical-oracle")
        self.best_actions: dict[str, MetaAction] = {}

    def decide(self, features: dict, executor: MetaActionExecutor) -> MetaAction:
        # For now, always use ROLLOUT_16 (highest compute, highest expected quality)
        if executor.can_afford(MetaAction.ROLLOUT_16):
            return MetaAction.ROLLOUT_16
        elif executor.can_afford(MetaAction.ROLLOUT_4):
            return MetaAction.ROLLOUT_4
        return MetaAction.ACT_NOW


class BasePolicy:
    """Simple base policy."""

    def __init__(self):
        self.sha256 = "frozen-ygo-base-v1-00000000"

    def predict(self, obs, legal_actions: list[int], env) -> dict:
        if not legal_actions:
            return {"action": 10, "confidence": 1.0}
        available = env.env.available_actions()
        best_score = -1
        best_action = legal_actions[0]
        for action_idx in legal_actions:
            if action_idx < len(available):
                action = available[action_idx]
                score = action.get("estimated_value", 0)
                if action["type"] == "attack":
                    score += 0.5
                elif action["type"] == "play_card":
                    card = action.get("card", {})
                    score += card.get("attack", 0) / max(1, card.get("cost", 1)) * 0.1
                if score > best_score:
                    best_score = score
                    best_action = action_idx
        return {"action": best_action, "confidence": 0.7}


def run_ygo_003(n_games: int = 50, budgets: list[int] = None):
    """Run YGO-003 resource allocation experiment."""
    if budgets is None:
        budgets = [500, 1000, 2000]  # LOW, MEDIUM, HIGH

    allocators = {
        "A0": UniformAllocator(),
        "A1": FixedThresholdAllocator(),
        "A2": BudgetTrackerAllocator(),
        "A3": ThresholdBudgetAllocator(),
        "A7": ThompsonAllocator(),
        "A8": EmpiricalOracle(),
    }

    base_policy = BasePolicy()
    results = []

    for budget in budgets:
        for alloc_name, allocator in allocators.items():
            print(f"\n=== {alloc_name}: {allocator.name} (budget={budget}) ===")

            for game_idx in range(n_games):
                seed = 42 + game_idx
                opponent = ["passive", "aggressive", "defensive"][game_idx % 3]

                env = make(seed=seed, opponent=opponent)
                obs = env.reset()
                done = False
                total_reward = 0.0
                executor = MetaActionExecutor(total_budget=budget)
                credits_used = 0
                meta_actions_taken = []

                while not done:
                    legal = env.legal_actions()
                    available = env.env.available_actions()

                    # Extract features
                    features = {
                        "estimated_uncertainty": abs(0.5 - (obs[0] / max(1, obs[0] + obs[1]))) * 2,
                        "branching_factor": len(legal),
                        "remaining_budget_fraction": executor.remaining_budget / max(1, budget),
                    }

                    # Allocator decides
                    meta_action = allocator.decide(features, executor)

                    # Base policy predicts
                    prediction = base_policy.predict(obs, legal, env)
                    action_idx = prediction["action"]

                    # Execute meta-action
                    exec_result = executor.execute(meta_action, action_idx, available)
                    credits_used += exec_result["spend"].credits
                    meta_actions_taken.append(meta_action.value)

                    # Take action
                    obs, reward, done, info = env.step(exec_result["modified_action"])
                    total_reward += reward

                    # Record outcome for Thompson
                    if isinstance(allocator, ThompsonAllocator):
                        allocator.record_outcome(meta_action, reward > 0)

                won = bool(obs[1] <= 0) if len(obs) > 1 else False

                results.append({
                    "allocator": alloc_name,
                    "budget": budget,
                    "game_idx": game_idx,
                    "won": won,
                    "total_reward": total_reward,
                    "credits_used": credits_used,
                    "meta_actions": meta_actions_taken,
                })

            # Print progress
            arm_results = [r for r in results if r["allocator"] == alloc_name and r["budget"] == budget]
            wins = sum(1 for r in arm_results if r["won"])
            print(f"  Win rate: {wins}/{len(arm_results)} ({wins/len(arm_results)*100:.0f}%)")

    # Aggregate
    summary = {}
    for alloc_name in allocators:
        for budget in budgets:
            key = f"{alloc_name}-budget-{budget}"
            arm_results = [r for r in results if r["allocator"] == alloc_name and r["budget"] == budget]
            if not arm_results:
                continue
            wins = sum(1 for r in arm_results if r["won"])
            n = len(arm_results)
            summary[key] = {
                "allocator": alloc_name,
                "budget": budget,
                "n": n,
                "win_rate": round(wins / n, 3),
                "avg_reward": round(sum(r["total_reward"] for r in arm_results) / n, 2),
                "avg_credits": round(sum(r["credits_used"] for r in arm_results) / n, 1),
            }

    # Save log
    run_id = f"ygo-003-{int(time.time())}"
    log_dir = Path("/root/mwgym/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_data = {
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "experiment": "YGO-003-ALLOCATOR",
        "runtime_class": "REAL",
        "n_games": n_games,
        "budgets": budgets,
        "allocators": list(allocators.keys()),
        "summary": summary,
        "results": results,
    }
    log_path = log_dir / f"{run_id}.json"
    log_path.write_text(json.dumps(log_data, indent=2))
    print(f"\nLog: {log_path}")

    # Print summary
    print(f"\n{'='*60}")
    print("YGO-003 RESULTS")
    print(f"{'='*60}")
    for key, stats in sorted(summary.items()):
        print(f"{stats['allocator']} (budget={stats['budget']}): "
              f"win_rate={stats['win_rate']*100:.0f}%, "
              f"reward={stats['avg_reward']}, "
              f"credits={stats['avg_credits']}")

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--budgets", type=str, default="500,1000,2000")
    args = parser.parse_args()
    budgets = [int(b) for b in args.budgets.split(",")]
    run_ygo_003(n_games=args.games, budgets=budgets)
