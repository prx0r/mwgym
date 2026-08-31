"""ModelCallRecord — canonical inference record."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelCallRecord:
    call_id: str = ""
    run_id: str = ""
    decision_id: str = ""

    harness: str = ""
    provider: str = ""
    model: str = ""

    started_at_ms: int = 0
    duration_ms: int = 0
    ttft_ms: int | None = None

    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    provider_request_id: str = ""
    finish_reason: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens + self.reasoning_tokens


@dataclass(frozen=True)
class ToolCallRecord:
    call_id: str = ""
    model_call_id: str = ""
    tool_name: str = ""
    arguments: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    external_cost_usd: float = 0.0
    x402_cost_usd: float = 0.0
    result_hash: str = ""
    success: bool = False

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass(frozen=True)
class RetrievalRecord:
    retrieval_id: str = ""
    run_id: str = ""
    decision_id: str = ""
    source: str = ""  # hydra, letta_memory, git
    query: str = ""
    results_count: int = 0
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class BudgetState:
    usd_remaining: float = 0.0
    model_requests_remaining: int = 0
    tool_calls_remaining: int = 0
    wall_seconds_remaining: float = 0.0
    tokens_remaining: int = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class DecisionPoint:
    decision_id: str = ""
    run_id: str = ""
    index: int = 0

    task_family: str = ""
    state_features: dict = field(default_factory=dict)

    budget_before: dict = field(default_factory=dict)
    candidate_actions: list[dict] = field(default_factory=list)
    selected_action: str = ""

    predicted_value: float | None = None
    predicted_cost: float | None = None
    uncertainty: float | None = None

    evidence_refs: list[str] = field(default_factory=list)

    model_call_ids: list[str] = field(default_factory=list)
    tool_call_ids: list[str] = field(default_factory=list)
    retrieval_ids: list[str] = field(default_factory=list)

    budget_after: dict = field(default_factory=dict)

    eventual_reward: float | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}
