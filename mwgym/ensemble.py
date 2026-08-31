"""Selective Ensemble (Avengers) — cheap disagreement → strong judge.

Multiple cheap workers attempt task independently.
If they agree: accept (no expensive model needed).
If they disagree: frontier model arbitrates.

This is the QDW selective ensemble routing policy.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .asset_profile import AssetProfileStore


@dataclass
class EnsembleVote:
    """A single worker's vote on a task."""
    worker_id: str = ""
    action: str = ""
    confidence: float = 0.0
    cost_usd: float = 0.0
    latency_ms: float = 0.0


@dataclass
class EnsembleResult:
    """Result of ensemble voting."""
    agreed: bool = False
    selected_action: str = ""
    votes: list[dict] = field(default_factory=list)
    agreement_score: float = 0.0
    needed_arbiter: bool = False
    arbiter_action: str = ""
    total_cost_usd: float = 0.0


class SelectiveEnsemble:
    """Avengers policy: cheap disagreement → strong judge.

    Usage:
    1. Spawn N cheap workers for same task
    2. Collect votes
    3. If agreement > threshold: accept majority vote
    4. If disagreement: invoke frontier model as arbiter
    """

    def __init__(self, profiles: AssetProfileStore = None,
                 agreement_threshold: float = 0.6,
                 n_cheap_workers: int = 3):
        self.profiles = profiles or AssetProfileStore()
        self.agreement_threshold = agreement_threshold
        self.n_cheap_workers = n_cheap_workers
        self.results: list[dict] = []

    def vote(self, votes: list[EnsembleVote]) -> EnsembleResult:
        """Process votes and determine if arbiter is needed."""
        if not votes:
            return EnsembleResult()

        # Count action votes
        action_counts: dict[str, list[EnsembleVote]] = {}
        for v in votes:
            if v.action not in action_counts:
                action_counts[v.action] = []
            action_counts[v.action].append(v)

        # Find majority action
        majority_action = max(action_counts, key=lambda a: len(action_counts[a]))
        majority_count = len(action_counts[majority_action])
        agreement_score = majority_count / len(votes)

        # Check if agreement is sufficient
        agreed = agreement_score >= self.agreement_threshold

        total_cost = sum(v.cost_usd for v in votes)

        result = EnsembleResult(
            agreed=agreed,
            selected_action=majority_action if agreed else "",
            votes=[{"worker": v.worker_id, "action": v.action, "confidence": v.confidence}
                   for v in votes],
            agreement_score=agreement_score,
            needed_arbiter=not agreed,
            total_cost_usd=total_cost,
        )

        self.results.append({
            "agreed": agreed,
            "agreement_score": agreement_score,
            "n_votes": len(votes),
            "actions": list(action_counts.keys()),
        })

        return result

    def should_use_ensemble(self, task_uncertainty: float,
                             budget_remaining: float) -> bool:
        """Decide if ensemble is worth the cost.

        Use ensemble when:
        - Uncertainty is high (disagreement likely)
        - Budget allows multiple cheap calls
        - Task is important enough to verify
        """
        if budget_remaining < 0.001:
            return False  # too expensive

        # High uncertainty → ensemble is valuable
        if task_uncertainty > 0.7:
            return True

        # Medium uncertainty + budget → ensemble
        if task_uncertainty > 0.4 and budget_remaining > 0.01:
            return True

        return False

    def summary(self) -> dict:
        total = len(self.results)
        agreed = sum(1 for r in self.results if r["agreed"])
        return {
            "total_ensemble_decisions": total,
            "agreed": agreed,
            "agreement_rate": agreed / max(1, total),
            "avg_agreement_score": sum(r["agreement_score"] for r in self.results) / max(1, total),
        }
