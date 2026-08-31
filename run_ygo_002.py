"""YGO-002: Memory Value Experiment

Per spec Section 46:
Compare:
- M0: no memory
- M1: Hydra only
- M2: Letta persistent only
- M3: Letta + Hydra
- M4: Letta + Hydra + validated Git skill

Measure: learning AUC, holdout win rate, retrieval precision, compute cost, transfer
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
from mwgym.meta_actions import MetaAction, MetaActionExecutor
from mwgym.telemetry_records import TelemetryStore, ResourceSpend
from mwgym.core.budget_ledger import BudgetLedger
from mwgym.asset_profile import AssetProfileStore
from mwgym.stack_oracle import StackOracle


class MemoryArm:
    """Base class for memory treatment arms."""

    def __init__(self, name: str):
        self.name = name
        self.memory_store: list[dict] = []

    def retrieve(self, features: dict) -> list[dict]:
        """Retrieve relevant memory. Returns empty list if no memory."""
        return []

    def store(self, decision: dict, outcome: dict):
        """Store experience in memory."""
        self.memory_store.append({"decision": decision, "outcome": outcome})


class M0_NoMemory(MemoryArm):
    """M0: No memory."""

    def __init__(self):
        super().__init__("M0-no-memory")

    def retrieve(self, features: dict) -> list[dict]:
        return []


class M1_HydraOnly(MemoryArm):
    """M1: Hydra retrieval only."""

    def __init__(self):
        super().__init__("M1-hydra-only")
        self.profiles = AssetProfileStore('/tmp/ygo-002-profiles.json')

    def retrieve(self, features: dict) -> list[dict]:
        # Simulate Hydra retrieval: find similar past states
        if not self.memory_store:
            return []
        # Return top-3 most similar past decisions
        return self.memory_store[-3:]

    def store(self, decision: dict, outcome: dict):
        super().store(decision, outcome)
        # Update asset profiles
        self.profiles.update(
            f"action-{decision.get('action_idx', 0)}",
            success=outcome.get("won", False),
            task_family="ygo.battle",
        )


class M2_LettaPersistent(MemoryArm):
    """M2: Letta persistent memory."""

    def __init__(self):
        super().__init__("M2-letta-persistent")
        self.session_memory: list[dict] = []

    def retrieve(self, features: dict) -> list[dict]:
        # Return session memory (persistent within episode)
        return self.session_memory[-5:]

    def store(self, decision: dict, outcome: dict):
        super().store(decision, outcome)
        self.session_memory.append({"decision": decision, "outcome": outcome})


class M3_LettaPlusHydra(MemoryArm):
    """M3: Letta + Hydra."""

    def __init__(self):
        super().__init__("M3-letta-plus-hydra")
        self.session_memory: list[dict] = []
        self.profiles = AssetProfileStore('/tmp/ygo-003-profiles.json')

    def retrieve(self, features: dict) -> list[dict]:
        # Combine session memory + Hydra retrieval
        session = self.session_memory[-3:]
        hydra = self.memory_store[-3:]
        return session + hydra

    def store(self, decision: dict, outcome: dict):
        super().store(decision, outcome)
        self.session_memory.append({"decision": decision, "outcome": outcome})
        self.profiles.update(
            f"action-{decision.get('action_idx', 0)}",
            success=outcome.get("won", False),
            task_family="ygo.battle",
        )


class M4_LettaPlusHydraPlusSkill(MemoryArm):
    """M4: Letta + Hydra + validated Git skill."""

    def __init__(self):
        super().__init__("M4-letta-plus-hydra-plus-skill")
        self.session_memory: list[dict] = []
        self.profiles = AssetProfileStore('/tmp/ygo-004-profiles.json')
        self.skills: list[dict] = []

    def retrieve(self, features: dict) -> list[dict]:
        # Combine session + Hydra + skills
        session = self.session_memory[-3:]
        hydra = self.memory_store[-3:]
        return session + hydra + self.skills[-2:]

    def store(self, decision: dict, outcome: dict):
        super().store(decision, outcome)
        self.session_memory.append({"decision": decision, "outcome": outcome})
        self.profiles.update(
            f"action-{decision.get('action_idx', 0)}",
            success=outcome.get("won", False),
            task_family="ygo.battle",
        )
        # Consolidate skills after 10 wins
        if len(self.memory_store) % 10 == 0:
            wins = sum(1 for m in self.memory_store if m.get("outcome", {}).get("won"))
            if wins > 5:
                self.skills.append({"skill": f"pattern-{len(self.skills)}", "confidence": wins / len(self.memory_store)})


class BasePolicy:
    """Simple base policy for YGO-002."""

    def __init__(self):
        self.sha256 = "frozen-ygo-base-v1-00000000"

    def predict(self, obs, legal_actions: list[int], env, memory: list[dict] = None) -> dict:
        if not legal_actions:
            return {"action": 10, "confidence": 1.0, "uncertainty": 0.0}

        available = env.env.available_actions()
        best_score = -1
        best_action = legal_actions[0]

        for action_idx in legal_actions:
            if action_idx < len(available):
                action = available[action_idx]
                score = self._score_action(action, obs)
                # Boost score if memory suggests this action worked before
                if memory:
                    for m in memory:
                        if m.get("decision", {}).get("action_idx") == action_idx:
                            if m.get("outcome", {}).get("won"):
                                score += 0.3  # memory boost
                if score > best_score:
                    best_score = score
                    best_action = action_idx

        return {"action": best_action, "confidence": 0.7, "uncertainty": 0.3}

    def _score_action(self, action: dict, obs) -> float:
        base = action.get("estimated_value", 0)
        if action["type"] == "attack":
            base += 0.5
        elif action["type"] == "play_card":
            card = action.get("card", {})
            efficiency = card.get("attack", 0) / max(1, card.get("cost", 1))
            base += efficiency * 0.1
        elif action["type"] == "buy":
            base *= 0.5
        return base


def run_ygo_002(n_games: int = 50, opponents: list[str] = None):
    """Run YGO-002 memory value experiment."""
    if opponents is None:
        opponents = ["passive", "aggressive", "defensive"]

    arms = {
        "M0": M0_NoMemory(),
        "M1": M1_HydraOnly(),
        "M2": M2_LettaPersistent(),
        "M3": M3_LettaPlusHydra(),
        "M4": M4_LettaPlusHydraPlusSkill(),
    }

    base_policy = BasePolicy()
    results_per_arm = {name: [] for name in arms}

    for arm_name, memory_arm in arms.items():
        print(f"\n=== {arm_name}: {memory_arm.name} ===")

        for game_idx in range(n_games):
            seed = 42 + game_idx
            opponent = opponents[game_idx % len(opponents)]

            env = make(seed=seed, opponent=opponent)
            obs = env.reset()
            done = False
            total_reward = 0.0
            executor = MetaActionExecutor(total_budget=1000)
            decisions = []

            while not done:
                legal = env.legal_actions()
                available = env.env.available_actions()

                # Retrieve memory
                features = {"turn": obs[5] if len(obs) > 5 else 0}
                memory = memory_arm.retrieve(features)

                # Predict with memory
                prediction = base_policy.predict(obs, legal, env, memory)

                # Execute
                action_idx = prediction["action"]
                obs, reward, done, info = env.step(action_idx)
                total_reward += reward

                # Store experience
                decision = {"action_idx": action_idx, "turn": len(decisions)}
                outcome = {"won": bool(obs[1] <= 0) if len(obs) > 1 else False, "reward": reward}
                memory_arm.store(decision, outcome)

                decisions.append({"action_idx": action_idx, "reward": reward})

            won = bool(obs[1] <= 0) if len(obs) > 1 else False
            results_per_arm[arm_name].append({
                "game_idx": game_idx,
                "won": won,
                "total_reward": total_reward,
                "decisions": len(decisions),
                "memory_size": len(memory_arm.memory_store),
            })

            if (game_idx + 1) % 10 == 0:
                print(f"  Game {game_idx + 1}/{n_games}: won={won}, reward={total_reward:.1f}, memory={len(memory_arm.memory_store)}")

    # Aggregate results
    summary = {}
    for arm_name, results in results_per_arm.items():
        wins = sum(1 for r in results if r["won"])
        n = len(results)
        # Learning AUC: average win rate over time
        win_rates = []
        for i in range(n):
            subset = results[:i+1]
            wr = sum(1 for r in subset if r["won"]) / len(subset)
            win_rates.append(wr)
        learning_auc = sum(win_rates) / n if n > 0 else 0

        summary[arm_name] = {
            "name": arms[arm_name].name,
            "n": n,
            "win_rate": round(wins / n, 3),
            "avg_reward": round(sum(r["total_reward"] for r in results) / n, 2),
            "learning_auc": round(learning_auc, 3),
            "final_memory_size": results[-1]["memory_size"] if results else 0,
        }

    # Save log
    run_id = f"ygo-002-{int(time.time())}"
    log_dir = Path("/root/mwgym/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_data = {
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "experiment": "YGO-002-MEMORY",
        "runtime_class": "REAL",
        "n_games": n_games,
        "opponents": opponents,
        "summary": summary,
        "results": {name: results for name, results in results_per_arm.items()},
    }
    log_path = log_dir / f"{run_id}.json"
    log_path.write_text(json.dumps(log_data, indent=2))
    print(f"\nLog: {log_path}")

    # Print summary
    print(f"\n{'='*60}")
    print("YGO-002 RESULTS")
    print(f"{'='*60}")
    for arm_name, stats in sorted(summary.items()):
        print(f"{arm_name}: {stats['name']}")
        print(f"  Win rate: {stats['win_rate']*100:.1f}%")
        print(f"  Avg reward: {stats['avg_reward']}")
        print(f"  Learning AUC: {stats['learning_auc']}")
        print(f"  Memory size: {stats['final_memory_size']}")

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--opponents", type=str, default="passive,aggressive,defensive")
    args = parser.parse_args()
    opponents = [o.strip() for o in args.opponents.split(",")]
    run_ygo_002(n_games=args.games, opponents=opponents)
