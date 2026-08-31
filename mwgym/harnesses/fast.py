"""FastExecutor — one LLM call, no tools, ActionBundle output.

Letta owns the worker identity/memory.
Moltwork owns the execution loop.
One model call returns structured output.
Moltwork validates and applies.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

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
    env_path = Path("/root/workerkit/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    _env_loaded = True


class FastExecutor:
    """One-shot execution via Letta with no tools."""

    def __init__(self, runtime_url: str = "http://localhost:3000"):
        self.runtime_url = runtime_url

    def _request(self, method: str, path: str, body: dict = None, timeout: int = 30) -> dict:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.runtime_url + path, data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())

    def provision(self, genome: WorkerGenome, worker_id: str) -> HarnessInstance:
        return HarnessInstance(harness="fast", worker_id=worker_id)

    def run(self, instance: HarnessInstance, task: str, workspace: str,
            policy: ExecutionPolicy = None) -> HarnessRun:
        policy = policy or ExecutionPolicy.fast()
        t0 = time.time()
        _load_env()

        # Build context pack (Moltwork does retrieval, not the model)
        context_pack = self._build_context_pack(task, workspace)

        # Ask model for structured ActionBundle
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

        data = json.dumps({
            "model": "mimo-v2.5",
            "messages": messages,
            "max_tokens": 4096,
            "thinking": {"type": "disabled"},
        }).encode()

        req = urllib.request.Request(
            api_url, data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            resp = urllib.request.urlopen(req, timeout=policy.max_wall_seconds)
            result = json.loads(resp.read())
            output = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = result.get("usage", {})
            duration_ms = int((time.time() - t0) * 1000)

            # Parse ActionBundle
            writes = []
            try:
                # Find JSON in output
                start = output.find("{")
                end = output.rfind("}") + 1
                if start >= 0 and end > start:
                    bundle = json.loads(output[start:end])
                    writes = bundle.get("writes", [])
            except json.JSONDecodeError:
                pass

            # Apply writes (Moltwork validates and executes)
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
                total_cost_usd=0.0,
            )

            return HarnessRun(
                ok=len(applied) > 0,
                output=output,
                artifacts=[str(ws / a) for a in applied],
                model_calls=[model_call.to_dict()],
                duration_ms=duration_ms,
                cost_usd=0.0,
                total_tokens=model_call.total_tokens,
            )
        except Exception as e:
            return HarnessRun(ok=False, output=str(e), duration_ms=int((time.time() - t0) * 1000))

    def _build_context_pack(self, task: str, workspace: str) -> str:
        """Build context pack — Moltwork does retrieval, model just thinks."""
        ws = Path(workspace)
        files = list(ws.rglob("*")) if ws.exists() else []
        file_list = "\n".join(f"  {f.name}" for f in files[:10]) if files else "  (empty workspace)"

        return f"""Task: {task}

Workspace files:
{file_list}

Return an ActionBundle with the required file writes."""
