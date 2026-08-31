"""FastExecutor — one LLM call, no tools, ActionBundle output.

Letta owns the worker identity/memory.
Moltwork owns the execution loop.
One model call returns structured output.
Moltwork validates and applies.
"""
from __future__ import annotations

import http.client
import json
import os
import ssl
import time
from pathlib import Path
from urllib.parse import urlparse

from ..schema.genome import WorkerGenome
from ..schema.execution_policy import ExecutionPolicy
from ..schema.telemetry import ModelCallRecord
from .base import HarnessInstance, HarnessRun


# Load API key from .env
_env_loaded = False
def _load_env():
    global _env_loaded
    if _env_loaded:
        return
    for p in [Path("/root/workerkit/.env"), Path("/root/.env")]:
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    _env_loaded = True


class FastExecutor:
    """One-shot execution via Letta with no tools."""

    def __init__(self, runtime_url: str = "http://localhost:3000"):
        self.runtime_url = runtime_url

    def provision(self, genome: WorkerGenome, worker_id: str) -> HarnessInstance:
        return HarnessInstance(harness="fast", worker_id=worker_id)

    def run(self, instance: HarnessInstance, task: str, workspace: str,
            policy: ExecutionPolicy = None) -> HarnessRun:
        policy = policy or ExecutionPolicy.fast()
        t0 = time.time()
        _load_env()

        context_pack = self._build_context_pack(task, workspace)

        system = """You are a worker. Return a JSON ActionBundle with file writes.
No tool calls needed. Just return the JSON.

ActionBundle format:
{
  "status": "complete",
  "writes": [{"path": "filename", "content": "file content"}],
  "notes": "what you did"
}"""

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": context_pack},
        ]

        api_key = os.environ.get("OPENCODE_API_KEY", "")
        api_url = os.environ.get("OPENCODE_API_URL", "https://opencode.ai/zen/go/v1/chat/completions")

        payload = json.dumps({
            "model": "mimo-v2.5",
            "messages": messages,
            "max_tokens": 4096,
            "thinking": {"type": "disabled"},
        })

        parsed = urlparse(api_url)
        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection(parsed.hostname, context=ctx, timeout=policy.max_wall_seconds)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

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

            final_output = output or reasoning or ""

            # Parse ActionBundle
            writes = []
            try:
                start = final_output.find("{")
                end = final_output.rfind("}") + 1
                if start >= 0 and end > start:
                    bundle = json.loads(final_output[start:end])
                    writes = bundle.get("writes", [])
            except json.JSONDecodeError:
                pass

            # Apply writes
            ws = Path(workspace)
            ws.mkdir(parents=True, exist_ok=True)
            applied = []
            for w in writes:
                path = ws / w["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(w["content"])
                applied.append(w["path"])

            model_call = ModelCallRecord(
                call_id=f"mc-{int(time.time()*1000)}",
                run_id=instance.session_id,
                harness="fast",
                provider="opencode-go",
                model="mimo-v2.5",
                started_at_ms=int(t0 * 1000),
                duration_ms=duration_ms,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                reasoning_tokens=usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
                total_cost_usd=0.0,
            )

            return HarnessRun(
                ok=len(applied) > 0 or bool(final_output),
                output=final_output,
                artifacts=[str(ws / a) for a in applied],
                model_calls=[model_call.to_dict()],
                duration_ms=duration_ms,
                cost_usd=0.0,
                total_tokens=model_call.total_tokens,
            )
        except Exception as e:
            return HarnessRun(ok=False, output=str(e), duration_ms=int((time.time() - t0) * 1000))
        finally:
            conn.close()

    def _build_context_pack(self, task: str, workspace: str) -> str:
        ws = Path(workspace)
        files = list(ws.rglob("*")) if ws.exists() else []
        file_list = "\n".join(f"  {f.name}" for f in files[:10]) if files else "  (empty workspace)"

        return f"""Task: {task}

Workspace files:
{file_list}

Return an ActionBundle with the required file writes."""
