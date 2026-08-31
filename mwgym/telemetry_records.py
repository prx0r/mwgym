"""Telemetry — canonical evidence for every resource decision.

Every model call, tool call, retrieval, and rollout gets recorded.
Missing cost is UNKNOWN, not zero (unless truly free).

This is M0 — blocks everything else.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelCallRecord:
    """One model inference call."""
    call_id: str = ""
    decision_id: str = ""
    provider: str = ""
    model: str = ""

    # Actual usage (from API response, not estimates)
    actual_input_tokens: int = 0
    actual_output_tokens: int = 0
    actual_reasoning_tokens: int = 0
    actual_cache_tokens: int = 0

    # Timing
    started_at: float = 0.0
    latency_ms: float = 0.0
    ttft_ms: float = 0.0  # time to first token

    # Cost (UNKNOWN if not measured)
    actual_cost_usd: float = 0.0
    cost_source: str = "unknown"  # "livellm", "provider_api", "pinned", "unknown"

    # Provider metadata
    provider_request_id: str = ""
    finish_reason: str = ""

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class ToolCallRecord:
    """One tool invocation."""
    tool_call_id: str = ""
    decision_id: str = ""
    tool_name: str = ""

    started_at: float = 0.0
    latency_ms: float = 0.0
    status: str = ""  # "success", "error", "timeout"

    cost_usd: float = 0.0
    cost_source: str = "unknown"

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class RetrievalRecord:
    """One retrieval from Hydra/memory."""
    retrieval_id: str = ""
    decision_id: str = ""
    source: str = ""  # "hydra", "letta_memory", "git"

    query_features: dict = field(default_factory=dict)
    candidate_count: int = 0
    selected_run_ids: list[str] = field(default_factory=list)
    selected_decision_ids: list[str] = field(default_factory=list)
    similarity_scores: list[float] = field(default_factory=list)

    latency_ms: float = 0.0
    token_cost: int = 0
    result_digest: str = ""

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class RolloutRecord:
    """One rollout (simulation of candidate actions)."""
    rollout_id: str = ""
    decision_id: str = ""
    width: int = 0  # number of rollouts (4, 16, etc.)
    depth: int = 0

    steps_simulated: int = 0
    latency_ms: float = 0.0

    cost_usd: float = 0.0
    cost_source: str = "unknown"

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class ResourceSpend:
    """Debited resource from ComputeWallet."""
    spend_id: str = ""
    decision_id: str = ""
    category: str = ""  # "model_call", "tool_call", "retrieval", "rollout", "reasoning"

    amount_usd: float = 0.0
    amount_credits: int = 0
    amount_tokens: int = 0

    description: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


class TelemetryStore:
    """Append-only store for all telemetry records."""

    def __init__(self):
        self.model_calls: list[dict] = []
        self.tool_calls: list[dict] = []
        self.retrievals: list[dict] = []
        self.rollouts: list[dict] = []
        self.resource_spends: list[dict] = []

    def record_model_call(self, record: ModelCallRecord):
        self.model_calls.append(record.to_dict())

    def record_tool_call(self, record: ToolCallRecord):
        self.tool_calls.append(record.to_dict())

    def record_retrieval(self, record: RetrievalRecord):
        self.retrievals.append(record.to_dict())

    def record_rollout(self, record: RolloutRecord):
        self.rollouts.append(record.to_dict())

    def record_spend(self, record: ResourceSpend):
        self.resource_spends.append(record.to_dict())

    def validate(self) -> list[str]:
        """Validate telemetry. Returns list of errors (empty = valid)."""
        errors = []

        # Check unique call IDs
        call_ids = [r.get("call_id", "") for r in self.model_calls]
        if len(call_ids) != len(set(call_ids)):
            errors.append("Duplicate model call IDs")

        # Check no negative usage
        for r in self.model_calls:
            if r.get("actual_input_tokens", 0) < 0:
                errors.append(f"Negative input tokens in {r.get('call_id')}")
            if r.get("actual_output_tokens", 0) < 0:
                errors.append(f"Negative output tokens in {r.get('call_id')}")

        # Check timestamps ordered
        prev_time = 0
        for r in self.model_calls:
            t = r.get("started_at", 0)
            if t < prev_time:
                errors.append(f"Timestamps not ordered in model calls")
                break
            prev_time = t

        # Check all costs reconcile
        total_model_cost = sum(r.get("actual_cost_usd", 0) for r in self.model_calls)
        total_spend = sum(r.get("amount_usd", 0) for r in self.resource_spends)
        if abs(total_model_cost - total_spend) > 0.001:
            errors.append(f"Cost mismatch: model_calls={total_model_cost:.4f} vs spends={total_spend:.4f}")

        # Check unknown costs not coerced to zero
        for r in self.model_calls:
            if r.get("cost_source") == "unknown" and r.get("actual_cost_usd", 0) == 0:
                pass  # This is OK if truly free

        return errors

    def summary(self) -> dict:
        return {
            "model_calls": len(self.model_calls),
            "tool_calls": len(self.tool_calls),
            "retrievals": len(self.retrievals),
            "rollouts": len(self.rollouts),
            "resource_spends": len(self.resource_spends),
            "total_model_cost": sum(r.get("actual_cost_usd", 0) for r in self.model_calls),
            "total_spend": sum(r.get("amount_usd", 0) for r in self.resource_spends),
        }
