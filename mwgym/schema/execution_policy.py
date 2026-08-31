"""ExecutionPolicy — three modes for WorkerRun execution."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExecutionMode(str, Enum):
    FAST = "fast"       # 1 LLM call, no tools, ActionBundle output
    BOUNDED = "bounded"  # 2-3 calls, Moltwork-owned loop
    AGENTIC = "agentic"  # full Letta Code loop


@dataclass
class ExecutionPolicy:
    mode: ExecutionMode = ExecutionMode.FAST

    max_model_calls: int = 1
    max_wall_seconds: float = 20
    max_cost_usd: float = 0.01

    context_strategy: str = "context_pack"  # context_pack, minimal, full
    output_schema: str = "action_bundle"  # action_bundle, patch, text

    allow_tools: bool = False
    toolset_base: str = "none"  # none, minimal, full

    @classmethod
    def fast(cls) -> ExecutionPolicy:
        return cls(
            mode=ExecutionMode.FAST,
            max_model_calls=1, max_wall_seconds=20, max_cost_usd=0.001,
            allow_tools=False, toolset_base="none", output_schema="action_bundle",
        )

    @classmethod
    def bounded(cls) -> ExecutionPolicy:
        return cls(
            mode=ExecutionMode.BOUNDED,
            max_model_calls=3, max_wall_seconds=90, max_cost_usd=0.01,
            allow_tools=False, toolset_base="none", output_schema="patch",
        )

    @classmethod
    def agentic(cls) -> ExecutionPolicy:
        return cls(
            mode=ExecutionMode.AGENTIC,
            max_model_calls=10, max_wall_seconds=300, max_cost_usd=0.05,
            allow_tools=True, toolset_base="minimal", output_schema="text",
        )

    def to_dict(self):
        return {k: v.value if isinstance(v, Enum) else v for k, v in self.__dict__.items()}
