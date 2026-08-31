"""ComputeWallet — multi-source budget with quota expiration.

Tracks: cash, Groq quota, OpenCode credits, local compute, free tiers.
Free quota is perishable inventory — expires if not used.
Shadow price increases as quota depletes or expiration approaches.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class QuotaSource:
    """A single compute quota source."""
    source_id: str = ""
    provider: str = ""  # groq, opencode, anthropic, local
    total: int = 0
    remaining: int = 0
    reset_interval_s: float = 3600.0  # 1 hour default
    last_reset: float = field(default_factory=time.time)
    expires_at: float = 0.0  # 0 = no expiration

    @property
    def is_expired(self) -> bool:
        if self.expires_at <= 0:
            return False
        return time.time() > self.expires_at

    @property
    def hours_until_reset(self) -> float:
        elapsed = time.time() - self.last_reset
        remaining = max(0, self.reset_interval_s - elapsed)
        return remaining / 3600

    @property
    def shadow_price(self) -> float:
        """Shadow price increases as quota depletes or expiration approaches.

        Low remaining + close to expiration = high shadow price.
        """
        if self.total <= 0:
            return 1.0

        # Depletion factor: 1.0 when full, approaches infinity when empty
        depletion = self.total / max(1, self.remaining)

        # Expiration factor: higher when expiration is soon
        if self.expires_at > 0:
            hours_left = max(0, (self.expires_at - time.time()) / 3600)
            expiration = 1.0 / max(0.1, hours_left)  # increases as time runs out
        else:
            expiration = 1.0

        # Reset factor: higher when reset is far away
        reset = 1.0 + (self.hours_until_reset / 24)  # 1.0-2.0 range

        return depletion * expiration * reset

    def use(self, amount: int = 1) -> bool:
        """Use quota. Returns False if not available."""
        if self.remaining < amount or self.is_expired:
            return False
        self.remaining -= amount
        return True

    def reset(self):
        """Reset quota (called when interval passes)."""
        self.remaining = self.total
        self.last_reset = time.time()

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "provider": self.provider,
            "total": self.total,
            "remaining": self.remaining,
            "shadow_price": round(self.shadow_price, 3),
            "hours_until_reset": round(self.hours_until_reset, 2),
            "is_expired": self.is_expired,
        }


class ComputeWallet:
    """Multi-source budget with quota expiration tracking."""

    def __init__(self):
        self.cash_usd: float = 0.0
        self.daily_cap_usd: float = 10.0
        self.spent_today_usd: float = 0.0
        self.quotas: dict[str, QuotaSource] = {}
        self._last_daily_reset: float = time.time()

    def add_quota(self, source_id: str, provider: str, total: int,
                   reset_interval_s: float = 3600, expires_at: float = 0):
        """Add a quota source."""
        self.quotas[source_id] = QuotaSource(
            source_id=source_id,
            provider=provider,
            total=total,
            remaining=total,
            reset_interval_s=reset_interval_s,
            expires_at=expires_at,
        )

    def can_afford(self, cost_usd: float = 0, quota_needed: int = 1,
                    provider: str = "") -> bool:
        """Check if we can afford a compute action."""
        # Check cash
        if self.spent_today_usd + cost_usd > self.daily_cap_usd:
            return False

        # Check quota
        if provider:
            for q in self.quotas.values():
                if q.provider == provider and not q.is_expired:
                    if q.remaining >= quota_needed:
                        return True
            return False

        # Any quota available
        return any(q.remaining >= quota_needed and not q.is_expired
                   for q in self.quotas.values())

    def spend(self, cost_usd: float = 0, quota_needed: int = 1,
              provider: str = "") -> bool:
        """Spend from wallet. Returns True if successful."""
        if not self.can_afford(cost_usd, quota_needed, provider):
            return False

        self.spent_today_usd += cost_usd

        # Spend quota
        if provider:
            for q in self.quotas.values():
                if q.provider == provider and not q.is_expired:
                    if q.use(quota_needed):
                        return True

        # Spend any quota
        for q in self.quotas.values():
            if not q.is_expired and q.remaining >= quota_needed:
                if q.use(quota_needed):
                    return True

        return True

    def best_free_option(self) -> QuotaSource | None:
        """Find the best free quota option (highest remaining, soonest reset)."""
        free_quotas = [q for q in self.quotas.values()
                       if not q.is_expired and q.remaining > 0]
        if not free_quotas:
            return None
        # Prefer: most remaining, then soonest reset
        return max(free_quotas, key=lambda q: (q.remaining, -q.hours_until_reset))

    def sweep_expiring(self, task_backlog: list[dict]) -> list[dict]:
        """Find tasks to run with expiring free compute.

        Returns tasks that have positive expected value and can be run cheaply.
        """
        sweepable = []
        for q in self.quotas.values():
            if q.is_expired or q.remaining <= 0:
                continue
            hours_left = q.hours_until_reset
            if hours_left < 1:  # expiring within 1 hour
                # Find tasks that match this provider and are low-risk
                for task in task_backlog:
                    if task.get("provider") == q.provider and task.get("risk", 0) < 0.3:
                        sweepable.append({
                            "task": task,
                            "quota": q.source_id,
                            "reason": f"expiring in {hours_left:.1f}h",
                        })
        return sweepable

    def shadow_prices(self) -> dict[str, float]:
        """Get shadow prices for all quota sources."""
        return {q.source_id: q.shadow_price for q in self.quotas.values()}

    def daily_report(self) -> dict:
        """Daily usage report."""
        return {
            "cash_usd": round(self.cash_usd, 4),
            "spent_today_usd": round(self.spent_today_usd, 4),
            "remaining_usd": round(max(0, self.daily_cap_usd - self.spent_today_usd), 4),
            "quotas": {k: v.to_dict() for k, v in self.quotas.items()},
            "shadow_prices": self.shadow_prices(),
        }
