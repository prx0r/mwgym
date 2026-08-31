"""Direct adapter — one-shot, no memory, cheapest baseline."""
from __future__ import annotations

import http.client
import json
import os
import ssl
import time
from pathlib import Path
from urllib.parse import urlparse

from ..schema.genome import WorkerGenome
from ..schema.telemetry import ModelCallRecord
from .base import HarnessInstance, HarnessRun, StateSnapshot


def _load_env():
    for env_path in [Path("/root/workerkit/.env"), Path("/root/.env")]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


class DirectAdapter:
    """Direct model call — one shot, no agent loop."""

    def __init__(self, api_url: str = ""):
        _load_env()
        self.api_url = api_url or os.environ.get(
            "OPENCODE_API_URL",
            "https://opencode.ai/zen/go/v1/chat/completions",
        )
        self.api_key = os.environ.get("OPENCODE_API_KEY", "")

    async def provision(self, genome: WorkerGenome, worker_id: str) -> HarnessInstance:
        return HarnessInstance(harness="direct", worker_id=worker_id)

    async def run(self, instance: HarnessInstance, task: str, workspace: str) -> HarnessRun:
        t0 = time.time()
        ws = Path(workspace)
        ws.mkdir(parents=True, exist_ok=True)

        system = "You are a file writer. Write exactly what is asked. No reasoning."
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ]

        payload = json.dumps({
            "model": "mimo-v2.5",
            "messages": messages,
            "max_tokens": 4096,
            "thinking": {"type": "disabled"},
        })

        parsed = urlparse(self.api_url)
        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection(parsed.hostname, context=ctx, timeout=30)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            conn.request("POST", parsed.path, body=payload, headers=headers)
            resp = conn.getresponse()
            body = resp.read().decode()
            if resp.status != 200:
                return HarnessRun(ok=False, output=f"HTTP {resp.status}: {body[:500]}",
                                  duration_ms=int((time.time() - t0) * 1000))

            result = json.loads(body)
            output = result.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
            reasoning = result.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "") or ""
            usage = result.get("usage", {})
            duration_ms = int((time.time() - t0) * 1000)

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
                reasoning_tokens=usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
                total_cost_usd=0.0,
            )

            # If model returned reasoning but no content, use reasoning as output
            final_output = output or reasoning or ""

            return HarnessRun(
                ok=True, output=final_output,
                model_calls=[model_call.to_dict()],
                duration_ms=duration_ms,
                cost_usd=0.0,
                total_tokens=model_call.total_tokens,
            )
        except Exception as e:
            return HarnessRun(ok=False, output=str(e), duration_ms=int((time.time() - t0) * 1000))
        finally:
            conn.close()

    async def snapshot(self, instance: HarnessInstance) -> StateSnapshot:
        return StateSnapshot(harness="direct", data={})

    async def restore(self, snapshot: StateSnapshot) -> HarnessInstance:
        return HarnessInstance(harness="direct")

    async def close(self, instance: HarnessInstance) -> None:
        pass
