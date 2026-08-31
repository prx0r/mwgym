"""ModelCall — canonical record for every inference request.

This is the observability layer. Without this, we can't measure
whether Letta is worth the cost.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelCall:
    call_id: str = ""
    run_id: str = ""
    decision_id: str = ""

    # Provider info
    provider: str = ""  # opencode-go, anthropic, openai
    model: str = ""  # mimo-v2.5, claude-opus-4
    reasoning_mode: str = "enabled"  # enabled, disabled

    # Timing
    started_at: float = 0.0
    ttft_ms: float = 0.0  # time to first token
    duration_ms: float = 0.0

    # Token usage
    prompt_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # Cost
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    # Agent context
    agent_step: int = 0  # which step in the agent loop
    stop_reason: str = ""  # end_turn, tool_call, max_steps
    provider_request_id: str = ""

    # What happened
    tool_called: str = ""  # if this call triggered a tool
    tool_result_ok: bool = False

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_letta_event(cls, event: dict, run_id: str = "", decision_id: str = "") -> ModelCall:
        """Create from a Letta stream event."""
        return cls(
            run_id=run_id,
            decision_id=decision_id,
            provider=event.get("provider", ""),
            model=event.get("model", ""),
            reasoning_mode=event.get("reasoning_mode", "enabled"),
            started_at=event.get("started_at", time.time()),
            duration_ms=event.get("duration_ms", 0),
            total_tokens=event.get("total_tokens", 0),
            tool_called=event.get("tool_name", ""),
            agent_step=event.get("step", 0),
        )


@dataclass
class ToolCall:
    call_id: str = ""
    model_call_id: str = ""
    tool_name: str = ""
    arguments: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    external_cost_usd: float = 0.0
    x402_cost_usd: float = 0.0
    result_hash: str = ""
    success: bool = False

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


@dataclass  
class RuntimeProfile:
    """What the worker genome says about how to run."""
    runtime: str = "letta"  # direct, letta-stateless, letta-stateful

    model_id: str = "opencode-go/mimo-v2.5"
    thinking: str = "disabled"  # enabled, disabled

    memory_mode: str = "stateful"  # none, stateful

    max_steps: int = 4
    tool_profile: str = "coding-minimal"  # coding-minimal, full

    # Budget
    max_model_calls: int = 4
    max_tokens: int = 12000
    max_wall_ms: int = 60000
    max_usd: float = 0.05

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def direct(cls) -> RuntimeProfile:
        """One-shot, no memory."""
        return cls(
            runtime="direct", thinking="disabled", memory_mode="none",
            max_steps=1, max_model_calls=1, max_tokens=2000, max_wall_ms=5000, max_usd=0.001,
        )

    @classmethod
    def letta_stateless(cls) -> RuntimeProfile:
        """Letta but no memory."""
        return cls(
            runtime="letta-stateless", thinking="disabled", memory_mode="none",
            max_steps=4, max_model_calls=4, max_tokens=8000, max_wall_ms=30000, max_usd=0.01,
        )

    @classmethod
    def letta_stateful(cls) -> RuntimeProfile:
        """Full Letta with memory."""
        return cls(
            runtime="letta-stateful", thinking="enabled", memory_mode="stateful",
            max_steps=8, max_model_calls=8, max_tokens=16000, max_wall_ms=60000, max_usd=0.05,
        )
