"""WorkerGenome — immutable/versioned policy configuration."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkerGenome:
    schema_version: str = "mwgym.worker-genome.v1"
    id: str = ""
    parent_id: str = ""
    generation: int = 0

    # Harness
    harness_kind: str = "direct"  # direct, letta, pydantic-ai
    harness_version: str = "pinned"

    # Model
    model_provider: str = "opencode-go"
    model_id: str = "mimo-v2.5"
    thinking: str = "disabled"  # enabled, disabled
    temperature: float = 0.0
    max_output_tokens: int = 4096

    # Memory
    memory_enabled: bool = False
    memory_mode: str = "none"  # none, stateful
    retrieval_top_k: int = 4
    max_context_tokens: int = 6000

    # Skills
    skills_enabled: bool = False
    skills_commit: str = ""

    # Planning
    planning_enabled: bool = False

    # Reasoning
    reasoning_policy: str = "fixed"  # fixed, adaptive

    # Tools
    tool_profile: str = "filesystem-minimal"  # filesystem-minimal, coding, full

    # Budget
    max_usd: float = 0.05
    max_model_requests: int = 6
    max_tool_calls: int = 20
    max_wall_seconds: int = 120

    # Reflection
    reflection_policy: str = "checkpoint"  # none, checkpoint, continuous
    reflection_every_runs: int = 50

    def hash(self) -> str:
        data = json.dumps(self.__dict__, sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> WorkerGenome:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def direct_fast(cls) -> WorkerGenome:
        return cls(
            id="direct-fast", harness_kind="direct",
            thinking="disabled", memory_enabled=False,
            max_model_requests=1, max_tool_calls=5, max_wall_seconds=10, max_usd=0.001,
        )

    @classmethod
    def letta_stateless(cls) -> WorkerGenome:
        return cls(
            id="letta-stateless", harness_kind="letta",
            thinking="disabled", memory_mode="none",
            max_model_requests=4, max_tool_calls=15, max_wall_seconds=60, max_usd=0.01,
        )

    @classmethod
    def letta_stateful(cls) -> WorkerGenome:
        return cls(
            id="letta-stateful", harness_kind="letta",
            thinking="enabled", memory_enabled=True, memory_mode="stateful",
            max_model_requests=8, max_tool_calls=30, max_wall_seconds=120, max_usd=0.05,
        )

    @classmethod
    def pydantic_coder(cls) -> WorkerGenome:
        return cls(
            id="pydantic-coder", harness_kind="pydantic-ai",
            thinking="disabled", memory_enabled=False,
            max_model_requests=4, max_tool_calls=20, max_wall_seconds=60, max_usd=0.02,
        )

    @classmethod
    def pydantic_code_mode(cls) -> WorkerGenome:
        return cls(
            id="pydantic-code-mode", harness_kind="pydantic-ai",
            thinking="disabled", tool_profile="code-mode",
            max_model_requests=2, max_tool_calls=50, max_wall_seconds=60, max_usd=0.02,
        )
