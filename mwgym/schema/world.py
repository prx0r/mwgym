"""WorldGenome + FailureVector — the adversarial world representation.

WorldGenome defines a synthetic executable world.
FailureVector captures what went wrong in a run, driving the adversary.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorldGenome:
    """Immutable description of an adversarial world configuration.

    CG compiles this into an actual executable state machine.
    The adversary evolves WorldGenomes; the worker never sees this schema.
    """
    schema_version: str = "mwgym.world-genome.v1"
    id: str = ""
    parent_id: str = ""
    generation: int = 0

    # What kind of world
    family_id: str = ""             # e.g. "software.bug_fix", "research.verification"
    task_family: str = ""           # maps to Oracle taxonomy

    # Difficulty / structure
    difficulty: int = 1             # 1-10, compositional (not monolithic)
    seed: int = 0

    # World structure (what exists)
    structure: dict = field(default_factory=dict)
    # e.g. {"n_sources": 17, "n_required_claims": 8, "dependency_depth": 3}

    # Information landscape (what the worker can see)
    information: dict = field(default_factory=dict)
    # e.g. {"observable_fraction": 0.65, "conflicting_sources": 0.25, "stale_sources": 0.20}

    # Resources available to the worker
    resources: dict = field(default_factory=dict)
    # e.g. {"search_budget_usd": 0.03, "free_calls": 8, "paid_calls": 2}

    # Dynamics (how the world changes)
    dynamics: dict = field(default_factory=dict)
    # e.g. {"state_changes_mid_episode": true}

    # Adversarial perturbations applied
    perturbations: dict = field(default_factory=dict)
    # e.g. {"entity_aliases": true, "numeric_near_misses": true}

    # Evaluator configuration
    evaluator: dict = field(default_factory=dict)
    # e.g. {"hard_gates": [...], "soft_dimensions": [...]}

    # Provenance
    parent_ids: tuple[str, ...] = ()
    provenance: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def hash(self) -> str:
        data = json.dumps(self.__dict__, sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["parent_ids"] = list(d["parent_ids"])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> WorldGenome:
        d = dict(d)
        if "parent_ids" in d and isinstance(d["parent_ids"], list):
            d["parent_ids"] = tuple(d["parent_ids"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class GateResult:
    """Result of a single hard gate evaluation."""
    gate_id: str = ""
    gate_name: str = ""
    passed: bool = False
    expected: str = ""
    actual: str = ""
    detail: str = ""


@dataclass(frozen=True)
class CapabilityScore:
    """Score for a specific capability dimension."""
    capability: str = ""        # e.g. "code.understand", "source.verify"
    score: float = 0.0          # 0.0 - 1.0
    n_samples: int = 0          # how many times this was measured
    confidence: float = 0.0     # posterior confidence


@dataclass(frozen=True)
class FailureVector:
    """What went wrong in a run. Drives the adversary's mutation choices.

    Every harness run should produce one of these. The adversary reads it
    to decide how to mutate the next WorldGenome.
    """
    schema_version: str = "mwgym.failure-vector.v1"
    run_id: str = ""
    world_genome_id: str = ""
    worker_genome_id: str = ""

    # Gate results
    gates: tuple[GateResult, ...] = ()
    gates_passed: int = 0
    gates_total: int = 0

    # Capability evidence
    capabilities: tuple[CapabilityScore, ...] = ()

    # Failure modes detected
    failure_modes: tuple[str, ...] = ()
    # e.g. ("stale_source_selected", "contradiction_ignored", "premature_commit")

    # Economic failures
    regret_usd: float = 0.0
    wasted_model_calls: int = 0
    wasted_tool_calls: int = 0
    unnecessary_paid_calls: int = 0

    # Quality metrics
    quality_score: float = 0.0   # overall 0-1
    correctness: float = 0.0
    completeness: float = 0.0
    efficiency: float = 0.0

    # Timing
    duration_ms: int = 0
    model_calls: int = 0
    tool_calls: int = 0

    # The worker's actual output hash
    output_hash: str = ""

    created_at: float = field(default_factory=time.time)

    @property
    def gate_pass_rate(self) -> float:
        return self.gates_passed / max(1, self.gates_total)

    @property
    def has_failure(self) -> bool:
        return self.gates_passed < self.gates_total or self.quality_score < 0.8

    @property
    def failure_severity(self) -> float:
        """0 = perfect, 1 = total failure."""
        gate_fail = 1.0 - self.gate_pass_rate
        quality_fail = 1.0 - self.quality_score
        return (gate_fail + quality_fail) / 2.0

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["gates"] = [g.__dict__ for g in self.gates]
        d["capabilities"] = [c.__dict__ for c in self.capabilities]
        d["failure_modes"] = list(d["failure_modes"])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> FailureVector:
        d = dict(d)
        gates = tuple(GateResult(**g) for g in d.pop("gates", []))
        capabilities = tuple(CapabilityScore(**c) for c in d.pop("capabilities", []))
        failure_modes = tuple(d.pop("failure_modes", []))
        return cls(
            **{k: v for k, v in d.items() if k in cls.__dataclass_fields__},
            gates=gates, capabilities=capabilities, failure_modes=failure_modes,
        )

    @classmethod
    def empty_success(cls, run_id: str = "") -> FailureVector:
        return cls(run_id=run_id, gates_passed=0, gates_total=0, quality_score=1.0)

    def weakest_capabilities(self, top_k: int = 3) -> list[str]:
        """Return capability names sorted by score ascending."""
        sorted_caps = sorted(self.capabilities, key=lambda c: c.score)
        return [c.capability for c in sorted_caps[:top_k]]

    def dominant_failure_modes(self) -> list[str]:
        """Return failure modes, sorted by frequency in historical data."""
        return list(self.failure_modes)
