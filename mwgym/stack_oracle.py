"""StackOracle — generalized capability allocator.

Routes tasks to the best capability (model, tool, API, worker, human)
based on AssetProfile posteriors + LiveLLM pricing + budget constraints.

This is the QDW StackOracle primitive integrated with BATS economics.
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .asset_profile import AssetProfile, AssetProfileStore
from .core.budget_ledger import BudgetLedger


@dataclass
class CapabilityQuote:
    """A quote for a capability to handle a task."""
    asset_id: str = ""
    asset_type: str = ""  # model, tool, api, worker, human
    provider: str = ""
    price_usd: float = 0.0
    estimated_quality: float = 0.0
    latency_ms: float = 0.0
    available: bool = True
    free_quota_remaining: int = 0
    free_quota_reset_s: float = 0.0


@dataclass
class AllocationDecision:
    """The oracle's routing decision."""
    selected_asset: str = ""
    reason: str = ""
    expected_utility: float = 0.0
    expected_cost: float = 0.0
    expected_quality: float = 0.0
    alternatives: list[dict] = field(default_factory=list)
    exploration: bool = False  # was this a counterfactual exploration?
    budget_remaining: float = 0.0


class StackOracle:
    """Generalized capability allocator.

    Uses AssetProfile posteriors + pricing + budget to route tasks.
    """

    def __init__(self, profile_store: AssetProfileStore = None,
                 ledger: BudgetLedger = None):
        self.profiles = profile_store or AssetProfileStore()
        self.ledger = ledger or BudgetLedger(daily_cap=10.0, per_run_cap=2.0)
        self.decisions: list[dict] = []
        self._exploration_rate = 0.1  # 10% counterfactual exploration
        self._rng = random.Random()

    def allocate(self, task_family: str, task_value: float,
                  available_assets: list[str],
                  budget_remaining: float = None) -> AllocationDecision:
        """Route a task to the best capability.

        Args:
            task_family: what kind of task (e.g., "ygo.battle", "crossover.filesystem")
            task_value: how much is this task worth (for utility calculation)
            available_assets: which assets are eligible
            budget_remaining: how much budget is left

        Returns:
            AllocationDecision with selected asset and reasoning
        """
        if budget_remaining is None:
            budget_remaining = self.ledger.remaining()["per_run"]

        # Check if we can afford anything
        if budget_remaining <= 0:
            # Only free assets
            free_assets = [a for a in available_assets
                          if self.profiles.get(a).avg_cost_per_invocation <= 0]
            if free_assets:
                available_assets = free_assets
            else:
                return AllocationDecision(
                    selected_asset="",
                    reason="no_budget",
                    budget_remaining=budget_remaining,
                )

        # Thompson sampling across eligible assets
        ranked = self.profiles.rank(available_assets, task_value)

        # Counterfactual exploration: sometimes pick non-optimal
        exploration = False
        if self._rng.random() < self._exploration_rate and len(ranked) > 1:
            # Pick second-best or random
            if self._rng.random() < 0.5 and len(ranked) > 2:
                selected = ranked[self._rng.randint(1, len(ranked) - 1)]
            else:
                selected = ranked[1]
            exploration = True
        else:
            selected = ranked[0]

        # Build decision
        decision = AllocationDecision(
            selected_asset=selected["asset_id"],
            reason=f"thompson_select: p_success={selected['p_success']:.3f}, "
                   f"utility={selected['utility']:.4f}, cost={selected['cost']:.4f}",
            expected_utility=selected["utility"],
            expected_cost=selected["cost"],
            expected_quality=selected["p_success"],
            alternatives=ranked[1:5],  # top 4 alternatives
            exploration=exploration,
            budget_remaining=budget_remaining,
        )

        # Record decision
        self.decisions.append({
            "task_family": task_family,
            "selected": decision.selected_asset,
            "reason": decision.reason,
            "exploration": exploration,
            "timestamp": time.time(),
        })

        return decision

    def record_outcome(self, asset_id: str, success: bool, cost_usd: float = 0.0,
                       latency_ms: float = 0.0, task_family: str = ""):
        """Record the outcome of a routing decision."""
        self.profiles.update(asset_id, success, cost_usd, latency_ms, task_family)
        self.ledger.record(f"oracle-{asset_id}", "compute", cost_usd, 0,
                          f"{'success' if success else 'failure'}: {asset_id}")

    def set_exploration_rate(self, rate: float):
        """Set the counterfactual exploration rate."""
        self._exploration_rate = max(0.0, min(1.0, rate))

    def summary(self) -> dict:
        """Summary of oracle decisions."""
        total = len(self.decisions)
        explorations = sum(1 for d in self.decisions if d["exploration"])
        assets_used = set(d["selected"] for d in self.decisions)
        return {
            "total_decisions": total,
            "explorations": explorations,
            "exploration_rate": explorations / max(1, total),
            "unique_assets_used": len(assets_used),
            "assets_used": list(assets_used),
        }

    def set_exploration_budget(self, budget: int):
        """Set daily exploration quota to prevent selection bias."""
        self._exploration_budget = budget
        self._exploration_used = 0

    def reset_daily(self):
        """Reset daily counters."""
        self._exploration_used = 0
        self.ledger.reset_run()
