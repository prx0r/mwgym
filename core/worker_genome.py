"""WorkerGenome — the policy that controls how a worker allocates resources.

Four levels:
  L0: reasoning allocation (think/retrieve/verify/escalate)
  L1: execution allocation (which path/tool/sequence)
  L2: make/buy/lease (self/purchase/x402/worker)
  L3: opportunity allocation (which job/continue/abandon)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkerGenome:
    id: str = ""
    version: str = "v1"
    parent_id: str = ""

    # L0 — reasoning allocation
    think_threshold: float = 0.5  # probability below which to think more
    retrieve_threshold: float = 0.3  # similarity threshold for memory retrieval
    verify_threshold: float = 0.8  # quality below which to verify
    escalate_model_threshold: float = 0.9  # quality needed to use expensive model
    exploration_rate: float = 0.1  # probability of trying non-optimal option

    # L1 — execution allocation
    max_candidates: int = 3  # max parallel candidates to generate
    max_revisions: int = 2  # max revision rounds
    preferred_tools: list[str] = field(default_factory=list)
    timeout_per_step_s: float = 30.0

    # L2 — make/buy/lease
    self_build_threshold: float = 0.3  # cost below which to self-build
    buy_threshold: float = 0.5  # cost below which to buy
    lease_threshold: float = 1.0  # cost below which to lease
    min_quality_for_purchase: float = 0.7  # minimum quality for external purchase

    # L3 — opportunity allocation
    min_ev_for_entry: float = 0.5  # minimum expected value to start a job
    abort_threshold: float = -0.2  # marginal EV below which to abort
    max_concurrent_jobs: int = 1

    # Metadata
    task_families: list[str] = field(default_factory=list)  # specialized for these families
    created_at: float = 0.0
    generation: int = 0  # how many times this genome has been mutated

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}

    def hash(self) -> str:
        data = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def mutate(self, gene: str, delta: float) -> WorkerGenome:
        """Create a mutated copy."""
        import copy
        child = copy.deepcopy(self)
        child.parent_id = self.id
        child.id = f"{self.id}-mut-{gene}"
        child.version = f"v{self.generation + 1}"
        child.generation = self.generation + 1
        current = getattr(child, gene, None)
        if current is not None and isinstance(current, (int, float)):
            setattr(child, gene, max(0, current + delta))
        return child

    @classmethod
    def default(cls, task_family: str = "") -> WorkerGenome:
        return cls(
            id=f"wg-default-{task_family or 'general'}",
            task_families=[task_family] if task_family else [],
            created_at=0.0,
        )

    @classmethod
    def static(cls) -> WorkerGenome:
        """No memory, no learning, no exploration."""
        return cls(
            id="wg-static",
            exploration_rate=0.0,
            max_candidates=1,
            max_revisions=0,
        )

    @classmethod
    def memory(cls) -> WorkerGenome:
        """Uses memory but no BATS."""
        g = cls.default()
        g.id = "wg-memory"
        g.retrieve_threshold = 0.2
        return g

    @classmethod
    def memory_bats(cls) -> WorkerGenome:
        """Uses memory + BATS exploration."""
        g = cls.default()
        g.id = "wg-memory-bats"
        g.retrieve_threshold = 0.2
        g.exploration_rate = 0.15
        g.max_candidates = 3
        return g
