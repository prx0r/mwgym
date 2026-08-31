"""Letta harness — stateless and stateful execution via Letta-compatible API.

Since Letta may not be installed, this harness provides two modes:
- stateless: single model call, no memory (equivalent to direct but through Letta interface)
- stateful: maintains conversation history across calls within a run

Both use the same underlying API endpoint but differ in memory management.
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
from ..schema.telemetry import ModelCallRecord
from .base import HarnessInstance, HarnessRun


def _load_env():
    for env_path in [Path("/root/workerkit/.env"), Path("/root/.env")]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


class LettaAdapter:
    """Letta-compatible harness with stateless and stateful modes."""

    def __init__(self, api_url: str = ""):
        _load_env()
        self.api_url = api_url or os.environ.get(
            "OPENCODE_API_URL",
            "https://opencode.ai/zen/go/v1/chat/completions",
        )
        self.api_key = os.environ.get("OPENCODE_API_KEY", "")

    def _call_model(self, messages: list[dict], max_tokens: int = 4096,
                    thinking: str = "disabled") -> dict:
        """Make a single model call."""
        payload = json.dumps({
            "model": "mimo-v2.5",
            "messages": messages,
            "max_tokens": max_tokens,
            "thinking": {"type": thinking},
        })

        parsed = urlparse(self.api_url)
        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection(parsed.hostname, context=ctx, timeout=30)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        t0 = time.time()
        try:
            conn.request("POST", parsed.path, body=payload, headers=headers)
            resp = conn.getresponse()
            body = resp.read().decode()
            duration_ms = int((time.time() - t0) * 1000)

            if resp.status != 200:
                return {"ok": False, "error": f"HTTP {resp.status}: {body[:500]}",
                        "duration_ms": duration_ms}

            result = json.loads(body)
            output = result.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
            reasoning = result.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "") or ""
            usage = result.get("usage", {})

            return {
                "ok": True,
                "output": output or reasoning or "",
                "duration_ms": duration_ms,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
                "total_tokens": usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}
        finally:
            conn.close()

    def run_stateless(self, task: str, workspace: str, worker_id: str = "") -> HarnessRun:
        """Single model call, no memory. Equivalent to direct but with Letta interface."""
        t0 = time.time()

        system = "You are a worker. Complete the task. Return a JSON ActionBundle with file writes.\n\nActionBundle:\n{\"status\": \"complete\", \"writes\": [{\"path\": \"filename\", \"content\": \"content\"}], \"notes\": \"what you did\"}"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ]

        result = self._call_model(messages)
        duration_ms = int((time.time() - t0) * 1000)

        if not result["ok"]:
            return HarnessRun(ok=False, output=result["error"], duration_ms=duration_ms)

        output = result["output"]
        writes = []
        try:
            start = output.find("{")
            end = output.rfind("}") + 1
            if start >= 0 and end > start:
                bundle = json.loads(output[start:end])
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
            run_id=worker_id,
            harness="letta-stateless",
            provider="opencode-go",
            model="mimo-v2.5",
            started_at_ms=int(t0 * 1000),
            duration_ms=duration_ms,
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            reasoning_tokens=result["reasoning_tokens"],
            total_cost_usd=0.0,
        )

        return HarnessRun(
            ok=len(applied) > 0 or bool(output),
            output=output,
            artifacts=[str(ws / a) for a in applied],
            model_calls=[model_call.to_dict()],
            duration_ms=duration_ms,
            total_tokens=result["total_tokens"],
        )

    def run_stateful(self, task: str, workspace: str, worker_id: str = "",
                     max_steps: int = 4) -> HarnessRun:
        """Multi-step execution with conversation memory."""
        t0 = time.time()
        ws = Path(workspace)
        ws.mkdir(parents=True, exist_ok=True)

        system = """You are a stateful worker with memory. You can:
1. Write files by returning JSON: {"path": "name", "content": "data"}
2. Think step by step
3. Ask to continue if not done

When done, return: {"status": "complete", "notes": "summary"}
When you need to write a file, return ONLY the JSON for that file."""

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Task: {task}\n\nWorkspace: {workspace}\n\nBegin."},
        ]

        all_model_calls = []
        applied = []
        final_output = ""

        for step in range(max_steps):
            result = self._call_model(messages, max_tokens=2048)
            if not result["ok"]:
                break

            output = result["output"]
            final_output = output
            messages.append({"role": "assistant", "content": output})

            mc = ModelCallRecord(
                call_id=f"mc-{int(time.time()*1000)}",
                run_id=worker_id,
                harness="letta-stateful",
                provider="opencode-go",
                model="mimo-v2.5",
                started_at_ms=int(time.time() * 1000),
                duration_ms=result["duration_ms"],
                prompt_tokens=result["prompt_tokens"],
                completion_tokens=result["completion_tokens"],
                reasoning_tokens=result["reasoning_tokens"],
                total_cost_usd=0.0,
            )
            all_model_calls.append(mc.to_dict())

            # Try to parse file writes
            try:
                start = output.find("{")
                end = output.rfind("}") + 1
                if start >= 0 and end > start:
                    obj = json.loads(output[start:end])
                    if "path" in obj and "content" in obj:
                        path = ws / obj["path"]
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(obj["content"])
                        applied.append(obj["path"])
                        messages.append({"role": "user", "content": f"File {obj['path']} written. Continue or done?"})
                        continue
                    if obj.get("status") == "complete":
                        break
            except json.JSONDecodeError:
                pass

            # If no parseable JSON, ask to continue
            messages.append({"role": "user", "content": "Continue with the task."})

        duration_ms = int((time.time() - t0) * 1000)
        total_tokens = sum(mc.get("prompt_tokens", 0) + mc.get("completion_tokens", 0)
                          for mc in all_model_calls)

        return HarnessRun(
            ok=len(applied) > 0 or bool(final_output),
            output=final_output,
            artifacts=[str(ws / a) for a in applied],
            model_calls=all_model_calls,
            duration_ms=duration_ms,
            total_tokens=total_tokens,
        )
