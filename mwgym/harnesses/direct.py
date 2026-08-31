"""Direct adapter — one-shot, no memory, cheapest baseline."""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from ..schema.genome import WorkerGenome
from ..schema.telemetry import ModelCallRecord
from .base import HarnessInstance, HarnessRun, StateSnapshot


class DirectAdapter:
    """Direct model call — one shot, no agent loop."""

    def __init__(self, api_url: str = "https://opencode.ai/zen/go/v1/chat/completions"):
        self.api_url = api_url

    async def provision(self, genome: WorkerGenome, worker_id: str) -> HarnessInstance:
        return HarnessInstance(harness="direct", worker_id=worker_id)

    async def run(self, instance: HarnessInstance, task: str, workspace: str) -> HarnessRun:
        t0 = time.time()
        ws = Path(workspace)
        ws.mkdir(parents=True, exist_ok=True)

        # Single model call
        system = "You are a file writer. Write exactly what is asked. No reasoning."
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ]

        data = json.dumps({
            "model": "mimo-v2.5",
            "messages": messages,
            "max_tokens": 4096,
            "thinking": {"type": "disabled"},
        }).encode()

        req = urllib.request.Request(
            self.api_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )

        try:
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read())
            output = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = result.get("usage", {})

            duration_ms = int((time.time() - t0) * 1000)

            # Record model call
            model_call = ModelCallRecord(
                call_id=f"mc-{int(time.time()*1000)}",
                run_id=instance.session_id,
                harness="direct",
                provider="opencode-go",
                model="mimo-v2.5",
                started_at_ms=int(t0 * 1000),
                duration_ms=duration_ms,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_cost_usd=0.0,  # free tier
            )

            return HarnessRun(
                ok=True, output=output,
                model_calls=[model_call.to_dict()],
                duration_ms=duration_ms,
                cost_usd=0.0,
                total_tokens=model_call.total_tokens,
            )
        except Exception as e:
            return HarnessRun(ok=False, output=str(e), duration_ms=int((time.time() - t0) * 1000))

    async def snapshot(self, instance: HarnessInstance) -> StateSnapshot:
        return StateSnapshot(harness="direct", data={})

    async def restore(self, snapshot: StateSnapshot) -> HarnessInstance:
        return HarnessInstance(harness="direct")

    async def close(self, instance: HarnessInstance) -> None:
        pass
