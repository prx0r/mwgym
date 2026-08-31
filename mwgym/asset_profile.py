"""AssetProfile — Beta posterior for capability routing.

Each capability (model, tool, API, worker) gets an AssetProfile that tracks:
- Success/failure counts (Beta distribution)
- Cost history
- Latency history
- Task family specialization

Thompson sampling: sample from posterior → compute expected utility → route.

This is the QDW AssetProfile primitive integrated with BATS economics.
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def beta_sample(alpha: float, beta: float, rng: random.Random = None) -> float:
    """Sample from Beta distribution using Jöhnk's algorithm."""
    rng = rng or random.Random()
    if alpha <= 0 or beta <= 0:
        return 0.5
    # Use Python's built-in variate method
    return rng.betavariate(alpha, beta)


@dataclass
class AssetProfile:
    """Empirical profile for a capability asset.

    Tracks success/failure via Beta posterior for Thompson sampling.
    """
    asset_id: str = ""
    asset_type: str = ""  # model, tool, api, worker, human
    task_family: str = ""  # which task family this profile is for

    # Beta posterior: P(success | asset, task_family)
    alpha: int = 1  # successes + prior
    beta: int = 1   # failures + prior

    # Cost tracking
    total_cost_usd: float = 0.0
    total_invocations: int = 0
    avg_cost_per_invocation: float = 0.0

    # Latency tracking
    total_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    latencies: list[float] = field(default_factory=list)

    # Task family specialization
    task_families: dict[str, dict] = field(default_factory=dict)
    # {task_family: {alpha, beta, avg_cost, avg_latency}}

    # Metadata
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    version: int = 0

    def sample_success(self, rng: random.Random = None) -> float:
        """Thompson sample: what's the probability this asset succeeds?"""
        return beta_sample(self.alpha, self.beta, rng)

    def expected_utility(self, task_value: float, rng: random.Random = None) -> float:
        """Expected utility = P(success) * value - cost.

        This is the core routing metric.
        """
        p_success = self.sample_success(rng)
        return p_success * task_value - self.avg_cost_per_invocation

    def update(self, success: bool, cost_usd: float = 0.0, latency_ms: float = 0.0,
               task_family: str = ""):
        """Update posterior with new observation."""
        if success:
            self.alpha += 1
        else:
            self.beta += 1

        self.total_cost_usd += cost_usd
        self.total_invocations += 1
        self.avg_cost_per_invocation = self.total_cost_usd / self.total_invocations

        self.total_latency_ms += latency_ms
        self.avg_latency_ms = self.total_latency_ms / self.total_invocations
        self.latencies.append(latency_ms)
        if len(self.latencies) > 100:
            self.latencies = sorted(self.latencies)[-100:]
        self.p95_latency_ms = self.latencies[int(len(self.latencies) * 0.95)] if self.latencies else 0

        # Update task family specialization
        if task_family:
            if task_family not in self.task_families:
                self.task_families[task_family] = {"alpha": 1, "beta": 1, "total_cost": 0.0, "n": 0}
            tf = self.task_families[task_family]
            if success:
                tf["alpha"] += 1
            else:
                tf["beta"] += 1
            tf["total_cost"] += cost_usd
            tf["n"] += 1

        self.last_updated = time.time()
        self.version += 1

    def win_rate(self) -> float:
        """Observed win rate."""
        total = self.alpha + self.beta - 2  # subtract prior
        if total <= 0:
            return 0.5
        return (self.alpha - 1) / total

    def confidence(self) -> float:
        """How confident are we in this profile? Higher with more data."""
        total = self.alpha + self.beta - 2
        return min(1.0, total / 100)  # max confidence at 100 observations

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "task_family": self.task_family,
            "alpha": self.alpha,
            "beta": self.beta,
            "win_rate": round(self.win_rate(), 3),
            "confidence": round(self.confidence(), 3),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "avg_cost_per_invocation": round(self.avg_cost_per_invocation, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "total_invocations": self.total_invocations,
            "task_families": self.task_families,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AssetProfile:
        p = cls(
            asset_id=d.get("asset_id", ""),
            asset_type=d.get("asset_type", ""),
            task_family=d.get("task_family", ""),
            alpha=d.get("alpha", 1),
            beta=d.get("beta", 1),
            total_cost_usd=d.get("total_cost_usd", 0.0),
            total_invocations=d.get("total_invocations", 0),
            avg_cost_per_invocation=d.get("avg_cost_per_invocation", 0.0),
            avg_latency_ms=d.get("avg_latency_ms", 0.0),
            task_families=d.get("task_families", {}),
        )
        return p


class AssetProfileStore:
    """Persistent store for AssetProfiles."""

    def __init__(self, path: str = "/root/mwgym/data/asset-profiles.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.profiles: dict[str, AssetProfile] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                for k, v in data.items():
                    self.profiles[k] = AssetProfile.from_dict(v)
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self):
        data = {k: p.to_dict() for k, p in self.profiles.items()}
        self.path.write_text(json.dumps(data, indent=2))

    def get(self, asset_id: str) -> AssetProfile:
        if asset_id not in self.profiles:
            self.profiles[asset_id] = AssetProfile(asset_id=asset_id)
        return self.profiles[asset_id]

    def update(self, asset_id: str, success: bool, cost_usd: float = 0.0,
               latency_ms: float = 0.0, task_family: str = ""):
        profile = self.get(asset_id)
        profile.update(success, cost_usd, latency_ms, task_family)
        self._save()

    def thompson_select(self, asset_ids: list[str], task_value: float,
                         rng: random.Random = None) -> str:
        """Thompson sampling: select the best asset for a task."""
        rng = rng or random.Random()
        best_id = asset_ids[0] if asset_ids else ""
        best_utility = float("-inf")

        for aid in asset_ids:
            profile = self.get(aid)
            utility = profile.expected_utility(task_value, rng)
            if utility > best_utility:
                best_utility = utility
                best_id = aid

        return best_id

    def rank(self, asset_ids: list[str], task_value: float) -> list[dict]:
        """Rank assets by expected utility."""
        ranked = []
        for aid in asset_ids:
            profile = self.get(aid)
            p_success = profile.sample_success()
            utility = p_success * task_value - profile.avg_cost_per_invocation
            ranked.append({
                "asset_id": aid,
                "p_success": round(p_success, 3),
                "utility": round(utility, 4),
                "cost": round(profile.avg_cost_per_invocation, 4),
                "latency": round(profile.avg_latency_ms, 1),
                "confidence": round(profile.confidence(), 3),
            })
        return sorted(ranked, key=lambda x: x["utility"], reverse=True)
