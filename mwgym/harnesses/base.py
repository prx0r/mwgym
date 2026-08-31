"""HarnessAdapter — canonical interface for all execution harnesses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..schema.genome import WorkerGenome
from ..schema.telemetry import ModelCallRecord, ToolCallRecord


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
