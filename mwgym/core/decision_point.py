"""DecisionPoint — the atomic unit of lab intelligence.

Every worker run produces decision points:
- what to do
- what it cost
- what the alternatives were
- what actually happened
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DecisionOption:
    id: str = ""
    name: str = ""
    description: str = ""
    estimated_cost_usd: float = 0.0
    estimated_quality: float = 0.0
    estimated_latency_s: float = 0.0
    success_probability: float = 0.5
    type: str = ""  # self, buy, lease, x402, skip

    # Market context (populated by LiveLLM integration)
    market_model: str = ""
    market_provider: str = ""
    market_input_per_1m: float | None = None
    market_output_per_1m: float | None = None
    market_context_tokens: int | None = None
    market_quality_tier: str | None = None
    market_promotion: dict | None = None
    market_freshness: str = ""
    market_confidence: float | None = None
    market_source: str = ""  # "livellm" or "stale"


@dataclass
class DecisionPoint:
    id: str = ""
    run_id: str = ""
    task_family: str = ""

    # Context
    context_features: dict[str, float] = field(default_factory=dict)
    objective: str = ""

    # Budget at decision time
    budget_remaining_usd: float = 0.0
    budget_remaining_tokens: int = 0
    budget_remaining_minutes: float = 0.0

    # Options considered
    options: list[dict] = field(default_factory=list)
    selected_option_id: str = ""

    # Predictions
    predicted_cost_usd: float = 0.0
    predicted_quality: float = 0.0
    predicted_success_probability: float = 0.5

    # Actual outcome
    actual_cost_usd: float = 0.0
    actual_quality: float = 0.0
    actual_success: bool = False

    # Metadata
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}

    def record_outcome(self, cost: float, quality: float, success: bool):
        self.actual_cost_usd = cost
        self.actual_quality = quality
        self.actual_success = success
        self.completed_at = time.time()

    def regret(self) -> float:
        """How much better could the best option have been?"""
        if not self.options:
            return 0.0
        best_quality = max(o.get("estimated_quality", 0) for o in self.options)
        return best_quality - self.actual_quality

    def exploration_value(self) -> float:
        """Information gain from trying a non-obvious option."""
        if len(self.options) < 2:
            return 0.0
        # Higher value if we tried something with uncertain outcomes
        selected = next((o for o in self.options if o.get("id") == self.selected_option_id), {})
        return selected.get("estimated_quality", 0.5) * (1 - selected.get("success_probability", 0.5))
