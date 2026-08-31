"""Real Letta harness — uses the actual runtime-letta service on port 3000.

This is NOT a fake adapter. It calls the real Letta Agent SDK backend
through the workerkit runtime-letta service.

Each run creates a new Letta session (per LETTA-MVP-PLAN.md).
Worker identity persists across sessions via worker_id mapping.

Timing: Letta runs take ~35s-120s. Always use background execution.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

from ..schema.genome import WorkerGenome
from ..schema.telemetry import ModelCallRecord
from .base import HarnessInstance, HarnessRun


RUNTIME_LETTA_URL = os.environ.get("RUNTIME_LETTA_URL", "http://localhost:3000")


class RealLettaAdapter:
    """Real Letta harness using runtime-letta service.

    Key timing facts from previous experiments:
    - Letta runs take ~35s-120s per task
    - HTTP timeout must be >= 300s
    - runtime-letta hard timeout is 120s (configurable via body.timeout)
    - Always run tasks in background, never block on HTTP
    """

    def __init__(self, base_url: str = RUNTIME_LETTA_URL):
        self.base_url = base_url

    def _request(self, method: str, path: str, data: dict = None,
                 timeout: int = 300) -> dict:
        """Make HTTP request to runtime-letta.

        Default timeout 300s (5 minutes) to handle slow Letta runs.
        """
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)}

    def _ensure_worker(self, worker_id: str) -> str:
        """Ensure worker exists, return letta_agent_id."""
        result = self._request("GET", f"/workers/{worker_id}")
        if "error" not in result:
            return result.get("letta_agent_id", "")

        result = self._request("POST", "/workers", {
            "worker_id": worker_id,
            "model": "opencode-go/mimo-v2.5",
            "memory": [
                {"label": "persona", "value": "You are a Moltwork worker. Complete tasks precisely."},
                {"label": "moltwork", "value": "Use evidence. Follow requirements exactly."},
            ],
        })
        return result.get("letta_agent_id", "")

    def run(self, task: str, workspace: str, worker_id: str = "mwgym-default",
            genome: WorkerGenome = None, timeout: int = 180) -> HarnessRun:
        """Run a task using real Letta.

        Always runs with extended timeout (180s default).
        Letta runs take ~35s-120s. Never use short timeouts.
        """
        t0 = time.time()

        # Ensure worker exists
        agent_id = self._ensure_worker(worker_id)

        # Pass genome config and extended timeout to runtime-letta
        genome_config = {}
        if genome:
            genome_config = {
                "memory_mode": "letta" if genome.memory_enabled else "off",
                "max_steps": genome.max_model_requests,
                "reasoning_effort": "medium",
            }

        result = self._request("POST", f"/workers/{worker_id}/run", {
            "task": task,
            "workspace": workspace,
            "timeout": timeout,  # extended timeout for Letta
            "genome": genome_config,
            "toolset": {"base": "none", "include": ["Read", "LS", "Glob", "Grep", "Write"]},
        }, timeout=timeout + 30)  # HTTP timeout > Letta timeout

        duration_ms = int((time.time() - t0) * 1000)

        if "error" in result:
            return HarnessRun(ok=False, output=result["error"], duration_ms=duration_ms)

        output = result.get("output", "")
        artifacts = result.get("artifacts", [])
        model_calls = result.get("model_calls", [])

        return HarnessRun(
            ok=bool(output),
            output=output,
            artifacts=artifacts,
            model_calls=model_calls,
            duration_ms=duration_ms,
            cost_usd=0.0,
            total_tokens=sum(m.get("total_tokens", 0) for m in model_calls),
        )

    def run_background(self, task: str, workspace: str, worker_id: str = "mwgym-default",
                       genome: WorkerGenome = None, timeout: int = 180) -> dict:
        """Start a Letta run in background. Returns immediately with run info.

        The run continues in the background. Check status via _request.
        """
        self._ensure_worker(worker_id)

        genome_config = {}
        if genome:
            genome_config = {
                "memory_mode": "letta" if genome.memory_enabled else "off",
                "max_steps": genome.max_model_requests,
                "reasoning_effort": "medium",
            }

        # Start run (non-blocking)
        result = self._request("POST", f"/workers/{worker_id}/run", {
            "task": task,
            "workspace": workspace,
            "timeout": timeout,
            "genome": genome_config,
            "toolset": {"base": "none", "include": ["Read", "LS", "Glob", "Grep", "Write"]},
        }, timeout=30)  # Short timeout just to start

        return {
            "worker_id": worker_id,
            "started": True,
            "result": result,
        }

    def get_trajectory(self, worker_id: str) -> list[dict]:
        """Get trajectory from Letta for learning."""
        result = self._request("GET", f"/workers/{worker_id}/trajectory")
        return result.get("trajectory", [])

    def get_memfs(self, worker_id: str) -> dict:
        """Get MemFS state (Git-backed memory)."""
        result = self._request("GET", f"/workers/{worker_id}/memfs")
        return result.get("files", {})
