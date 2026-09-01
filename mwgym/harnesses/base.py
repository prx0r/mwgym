"""HarnessAdapter — canonical interface for all execution harnesses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..schema.genome import WorkerGenome
from ..schema.telemetry import ModelCallRecord, ToolCallRecord
from ..schema.world import (
    CapabilityScore, FailureVector, GateResult, WorldGenome,
)


@dataclass
class HarnessInstance:
    harness: str = ""
    worker_id: str = ""
    session_id: str = ""
    model_calls: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class HarnessRun:
    ok: bool = False
    output: str = ""
    artifacts: list[str] = field(default_factory=list)
    model_calls: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    duration_ms: int = 0
    cost_usd: float = 0.0
    total_tokens: int = 0
    metadata: dict = field(default_factory=dict)

    def to_failure_vector(self, world_genome_id: str = "",
                           worker_genome_id: str = "",
                           family_id: str = "",
                           gates: list[GateResult] | None = None,
                           capabilities: list[CapabilityScore] | None = None,
                           failure_modes: list[str] | None = None) -> FailureVector:
        """Produce a FailureVector from this harness run.

        Callers should override gates/capabilities/failure_modes for
        family-specific evaluation. This provides the economic telemetry.
        """
        # Detect generic failure modes
        modes = list(failure_modes or [])
        if not self.ok:
            modes.append("execution_failed")
        if self.cost_usd > 0.05:
            modes.append("high_cost")
        if self.duration_ms > 120000:
            modes.append("slow_execution")
        n_calls = len(self.model_calls) if isinstance(self.model_calls, list) else self.model_calls
        if n_calls > 10:
            modes.append("excessive_model_calls")
        if not self.artifacts:
            modes.append("no_artifacts")

        gate_list = tuple(gates or [])
        cap_list = tuple(capabilities or [])

        return FailureVector(
            run_id=self.metadata.get("run_id", ""),
            world_genome_id=world_genome_id,
            worker_genome_id=worker_genome_id,
            gates=gate_list,
            gates_passed=sum(1 for g in gate_list if g.passed),
            gates_total=len(gate_list),
            capabilities=cap_list,
            failure_modes=tuple(modes),
            quality_score=1.0 if self.ok else 0.0,
            correctness=self.metadata.get("correctness", 1.0 if self.ok else 0.0),
            completeness=self.metadata.get("completeness", 0.5),
            efficiency=max(0.0, 1.0 - self.cost_usd / 0.1),
            duration_ms=self.duration_ms,
            model_calls=n_calls,
            tool_calls=len(self.tool_calls) if isinstance(self.tool_calls, list) else self.tool_calls,
            output_hash=self.metadata.get("output_hash", ""),
        )


@dataclass
class StateSnapshot:
    harness: str = ""
    snapshot_id: str = ""
    data: dict = field(default_factory=dict)


class HarnessAdapter(Protocol):
    async def provision(self, genome: WorkerGenome, worker_id: str) -> HarnessInstance: ...
    async def run(self, instance: HarnessInstance, task: str, workspace: str) -> HarnessRun: ...
    async def snapshot(self, instance: HarnessInstance) -> StateSnapshot: ...
    async def restore(self, snapshot: StateSnapshot) -> HarnessInstance: ...
    async def close(self, instance: HarnessInstance) -> None: ...
