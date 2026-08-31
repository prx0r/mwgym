"""Letta adapter — persistent worker with memory."""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from ..schema.genome import WorkerGenome
from ..schema.telemetry import ModelCallRecord
from .base import HarnessInstance, HarnessRun, StateSnapshot


class LettaAdapter:
    """Letta harness — uses runtime-letta service."""

    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url

    def _request(self, method: str, path: str, body: dict = None, timeout: int = 30) -> dict:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())

    async def provision(self, genome: WorkerGenome, worker_id: str) -> HarnessInstance:
        # Ensure worker exists
        try:
            self._request("POST", "/workers", {
                "worker_id": worker_id,
                "model": f"{genome.model_provider}/{genome.model_id}",
            })
        except Exception:
            pass

        return HarnessInstance(
            harness="letta",
            worker_id=worker_id,
            metadata={"memory_mode": genome.memory_mode},
        )

    async def run(self, instance: HarnessInstance, task: str, workspace: str) -> HarnessRun:
        t0 = time.time()

        # Build session options based on genome
        body = {
            "task": task,
            "workspace": workspace,
            "timeout": 120,
        }

        try:
            result = self._request("POST", f"/workers/{instance.worker_id}/run", body, timeout=150)
            duration_ms = int((time.time() - t0) * 1000)

            # Parse tool calls from result
            tool_calls = result.get("tool_calls", [])

            return HarnessRun(
                ok=result.get("ok", False),
                output=result.get("output_content", ""),
                model_calls=[{"harness": "letta", "tool_calls": len(tool_calls)}],
                tool_calls=tool_calls,
                duration_ms=result.get("duration_ms", duration_ms),
                cost_usd=0.0,
                metadata={"conversation_id": result.get("conversation_id", "")},
            )
        except Exception as e:
            return HarnessRun(ok=False, output=str(e), duration_ms=int((time.time() - t0) * 1000))

    async def snapshot(self, instance: HarnessInstance) -> StateSnapshot:
        return StateSnapshot(harness="letta", data={"worker_id": instance.worker_id})

    async def restore(self, snapshot: StateSnapshot) -> HarnessInstance:
        return HarnessInstance(harness="letta", worker_id=snapshot.data.get("worker_id", ""))

    async def close(self, instance: HarnessInstance) -> None:
        pass
