"""BudgetLedger — track spending across decisions and runs."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BudgetEntry:
    decision_id: str = ""
    category: str = ""  # compute, purchase, lease, human
    amount_usd: float = 0.0
    tokens: int = 0
    description: str = ""
    timestamp: float = field(default_factory=time.time)


class BudgetLedger:
    def __init__(self, daily_cap: float = 10.0, per_run_cap: float = 2.0):
        self.daily_cap = daily_cap
        self.per_run_cap = per_run_cap
        self.entries: list[dict] = []
        self._daily_spent: float = 0.0
        self._run_spent: float = 0.0

    def record(self, decision_id: str, category: str, amount_usd: float, tokens: int = 0, description: str = ""):
        entry = BudgetEntry(
            decision_id=decision_id, category=category,
            amount_usd=amount_usd, tokens=tokens, description=description,
        )
        self.entries.append(entry.__dict__)
        self._daily_spent += amount_usd
        self._run_spent += amount_usd
        return entry

    def can_spend(self, amount: float) -> bool:
        return (self._run_spent + amount <= self.per_run_cap and
                self._daily_spent + amount <= self.daily_cap)

    def remaining(self) -> dict:
        return {
            "daily": max(0, self.daily_cap - self._daily_spent),
            "per_run": max(0, self.per_run_cap - self._run_spent),
        }

    def reset_run(self):
        self._run_spent = 0.0

    def total_spent(self) -> float:
        return sum(e.get("amount_usd", 0) for e in self.entries)

    def by_category(self) -> dict[str, float]:
        cats: dict[str, float] = {}
        for e in self.entries:
            cat = e.get("category", "unknown")
            cats[cat] = cats.get(cat, 0) + e.get("amount_usd", 0)
        return cats
