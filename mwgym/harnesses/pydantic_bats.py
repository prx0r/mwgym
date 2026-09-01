"""PydanticBATS — PydanticAI-style harness with BATS routing.

Core principles from pydantic-letta.md:
  - UsageLimits(request_limit=N) — hard request limit enforcement
  - Cost tracking per model call
  - Structured output (ActionBundle)
  - BATS routes to cheapest capable model

This is NOT the pydantic-ai package. It's a standalone implementation
following the same economic execution primitives.
"""
from __future__ import annotations

import http.client
import json
import os
import ssl
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..schema.world import (
    CapabilityScore, FailureVector, GateResult, WorldGenome,
)
from .base import HarnessInstance, HarnessRun


# ─── Usage Limits (PydanticAI concept) ───────────────────────────────

@dataclass
class UsageLimits:
    """Hard limits on execution. Enforced BEFORE every model request."""
    request_limit: int = 1          # max LLM calls
    cost_limit_usd: float = 0.05    # max total cost
    token_limit: int = 8000         # max total tokens
    tool_call_limit: int = 10       # max tool calls
    wall_time_limit_s: float = 60.0 # max wall time

    def can_afford(self, estimated_cost: float = 0.0,
                   estimated_tokens: int = 0) -> tuple[bool, str]:
        """Check if we can make another request. Returns (ok, reason)."""
        return True, ""  # overridden by tracker


@dataclass
class UsageTracker:
    """Tracks actual usage against limits. Enforced before every request."""
    limits: UsageLimits = field(default_factory=UsageLimits)
    requests_made: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    tool_calls_made: int = 0
    started_at: float = field(default_factory=time.time)

    def can_make_request(self, estimated_cost: float = 0.0) -> tuple[bool, str]:
        """Check if another request is allowed."""
        if self.requests_made >= self.limits.request_limit:
            return False, f"request_limit_reached ({self.limits.request_limit})"
        if self.total_cost_usd + estimated_cost > self.limits.cost_limit_usd:
            return False, f"cost_limit_exceeded ({self.total_cost_usd:.4f} + {estimated_cost:.4f} > {self.limits.cost_limit_usd:.4f})"
        wall_s = time.time() - self.started_at
        if wall_s > self.limits.wall_time_limit_s:
            return False, f"wall_time_exceeded ({wall_s:.1f}s > {self.limits.wall_time_limit_s}s)"
        return True, "ok"

    def record_request(self, cost_usd: float, tokens: int):
        self.requests_made += 1
        self.total_cost_usd += cost_usd
        self.total_tokens += tokens

    def record_tool_call(self):
        self.tool_calls_made += 1

    def to_dict(self) -> dict:
        return {
            "requests_made": self.requests_made,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_tokens": self.total_tokens,
            "tool_calls_made": self.tool_calls_made,
            "wall_time_s": round(time.time() - self.started_at, 2),
        }


# ─── BATS Model Router ───────────────────────────────────────────────

@dataclass
class ModelRoute:
    model: str = ""
    provider: str = ""
    api_url: str = ""
    api_key: str = ""
    reason: str = ""
    estimated_cost_per_call: float = 0.0
    quality_estimate: float = 0.0


class BATSRouter:
    """Budget-Aware Token Scheduler — routes to cheapest capable model."""

    MODELS = {
        "mimo-v2.5": {
            "provider": "opencode-go",
            "api_url": "https://opencode.ai/zen/go/v1/chat/completions",
            "quality": 0.7,
            "cost_per_1k_in": 0.0,
            "cost_per_1k_out": 0.0,
            "free": True,
        },
        "llama-3.3-70b-versatile": {
            "provider": "groq",
            "api_url": "https://api.groq.com/openai/v1/chat/completions",
            "quality": 0.85,
            "cost_per_1k_in": 0.00059,
            "cost_per_1k_out": 0.00079,
            "free": False,
        },
        "llama-3.1-8b-instant": {
            "provider": "groq",
            "api_url": "https://api.groq.com/openai/v1/chat/completions",
            "quality": 0.8,
            "cost_per_1k_in": 0.00005,
            "cost_per_1k_out": 0.00008,
            "free": False,
        },
    }

    def __init__(self):
        self._load_keys()

    def _load_keys(self):
        for env_path in [Path("/root/workerkit/.env"), Path("/root/.env")]:
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
        self._keys = {
            "opencode-go": os.environ.get("OPENCODE_API_KEY", ""),
            "groq": os.environ.get("GROQ_API_KEY", ""),
        }

    def select(self, task_type: str, budget_remaining: float,
               uncertainty: float = 0.5,
               capability_scores: dict[str, float] | None = None) -> ModelRoute:
        """Select model based on task, budget, and uncertainty."""
        # Tight budget → free
        if budget_remaining < 0.001:
            return self._route("mimo-v2.5", "budget_tight_free")

        # High uncertainty + budget → stronger model
        if uncertainty > 0.7 and budget_remaining > 0.01:
            # Check Hydra posterior for this task × model
            if capability_scores:
                for model_name in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
                    score = capability_scores.get(f"{model_name}.{task_type}", 0.5)
                    if score > 0.7:
                        return self._route(model_name, f"hydra_posterior_score={score:.2f}")

            # Default to cheap if budget allows
            return self._route("llama-3.3-70b-versatile", "high_uncertainty_budget_allows")

        # Check if free model is good enough from history
        if capability_scores:
            free_score = capability_scores.get(f"mimo-v2.5.{task_type}", 0.5)
            if free_score > 0.8:
                return self._route("mimo-v2.5", f"hydra_free_good_enough={free_score:.2f}")

        # Default: free
        return self._route("mimo-v2.5", "default_free")

    def _route(self, model_name: str, reason: str) -> ModelRoute:
        m = self.MODELS[model_name]
        key = self._keys.get(m["provider"], "")
        return ModelRoute(
            model=model_name,
            provider=m["provider"],
            api_url=m["api_url"],
            api_key=key,
            reason=reason,
            quality_estimate=m["quality"],
        )

    def estimate_cost(self, model_name: str, prompt_tokens: int,
                       completion_tokens: int) -> float:
        m = self.MODELS.get(model_name, {})
        return (
            prompt_tokens * m.get("cost_per_1k_in", 0) / 1000 +
            completion_tokens * m.get("cost_per_1k_out", 0) / 1000
        )


# ─── Model Caller ─────────────────────────────────────────────────────

def _call_model(api_url: str, api_key: str, model: str,
                messages: list[dict], max_tokens: int = 4096,
                thinking: str = "disabled",
                timeout: int = 30) -> dict:
    """Make a single model call."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "thinking": {"type": thinking},
    })

    parsed = urlparse(api_url)
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(parsed.hostname, context=ctx, timeout=timeout)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

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
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        reasoning = result.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "") or ""
        usage = result.get("usage", {})

        prompt_tok = usage.get("prompt_tokens", 0)
        comp_tok = usage.get("completion_tokens", 0)
        reason_tok = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)

        return {
            "ok": True,
            "content": content or reasoning or "",
            "reasoning": reasoning,
            "duration_ms": duration_ms,
            "prompt_tokens": prompt_tok,
            "completion_tokens": comp_tok,
            "reasoning_tokens": reason_tok,
            "total_tokens": prompt_tok + comp_tok,
            "model": model,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}
    finally:
        conn.close()


# ─── ActionBundle Parser ──────────────────────────────────────────────

def _parse_action_bundle(text: str) -> dict:
    """Parse ActionBundle JSON from model output."""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            bundle = json.loads(text[start:end])
            return {
                "status": bundle.get("status", "unknown"),
                "writes": bundle.get("writes", []),
                "notes": bundle.get("notes", ""),
                "answer": bundle.get("answer"),
            }
    except json.JSONDecodeError:
        pass
    return {"status": "parse_error", "writes": [], "notes": text[:200]}


# ─── PydanticBATS Harness ────────────────────────────────────────────

class PydanticBATSHarness:
    """PydanticAI-style harness with BATS routing.

    Core loop:
      1. BATS selects model based on budget + uncertainty
      2. UsageLimits enforced before every request
      3. Single model call returns ActionBundle
      4. Host applies writes
      5. Cost recorded to Hydra

    Usage:
      harness = PydanticBATSHarness()
      result = harness.run(task="...", workspace="/tmp/run-001",
                           limits=UsageLimits(request_limit=1, cost_limit_usd=0.01))
    """

    def __init__(self):
        self.router = BATSRouter()

    def run(self, task: str, workspace: str,
            limits: UsageLimits | None = None,
            world_genome_id: str = "",
            worker_genome_id: str = "",
            family_id: str = "",
            uncertainty: float = 0.5,
            capability_scores: dict[str, float] | None = None,
            context: str = "") -> tuple[HarnessRun, FailureVector]:
        """Execute a task with BATS routing and usage limits.

        Returns (HarnessRun, FailureVector).
        """
        limits = limits or UsageLimits()
        tracker = UsageTracker(limits=limits)
        t0 = time.time()
        ws = Path(workspace)
        ws.mkdir(parents=True, exist_ok=True)

        # BATS route
        route = self.router.select(
            task_type=family_id or "general",
            budget_remaining=limits.cost_limit_usd,
            uncertainty=uncertainty,
            capability_scores=capability_scores,
        )

        # Build messages
        system = (
            "You are a worker. Complete the task precisely.\n"
            "Return a JSON ActionBundle:\n"
            '{"status": "complete", "writes": [{"path": "file", "content": "data"}], '
            '"notes": "what you did"}'
        )
        user_msg = f"Task: {task}\n\nWorkspace: {workspace}"
        if context:
            user_msg += f"\n\nContext:\n{context}"
        user_msg += "\n\nReturn an ActionBundle with the required file writes."

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]

        # Check limits before request
        can, reason = tracker.can_make_request(route.estimated_cost_per_call)
        if not can:
            return self._make_result(
                ok=False, output=f"Budget exhausted: {reason}",
                workspace=workspace, t0=t0, tracker=tracker,
                route=route, world_genome_id=world_genome_id,
                worker_genome_id=worker_genome_id, family_id=family_id,
                gates=[], failure_modes=["budget_exhausted"],
            )

        # Single model call
        result = _call_model(
            api_url=route.api_url,
            api_key=route.api_key,
            model=route.model,
            messages=messages,
            max_tokens=4096,
            thinking="disabled",
            timeout=int(limits.wall_time_limit_s),
        )

        if not result["ok"]:
            return self._make_result(
                ok=False, output=f"Model error: {result['error']}",
                workspace=workspace, t0=t0, tracker=tracker,
                route=route, world_genome_id=world_genome_id,
                worker_genome_id=worker_genome_id, family_id=family_id,
                gates=[], failure_modes=["model_error"],
            )

        # Record request
        cost = self.router.estimate_cost(
            route.model, result["prompt_tokens"], result["completion_tokens"]
        )
        tracker.record_request(cost, result["total_tokens"])

        # Parse output
        output = result["content"]
        bundle = _parse_action_bundle(output)

        # Apply writes
        applied = []
        for w in bundle.get("writes", []):
            if isinstance(w, dict) and "path" in w and "content" in w:
                path = ws / w["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(w["content"])
                applied.append(w["path"])

        # Git commit
        git_hash = self._git_commit(workspace, f"pydantic-bats: {bundle.get('notes', task[:60])}")

        duration_ms = int((time.time() - t0) * 1000)

        # Build gates
        gates = [
            GateResult(gate_id="g0", gate_name="model_call",
                       passed=True, actual="ok"),
            GateResult(gate_id="g1", gate_name="output_parsed",
                       passed=bundle["status"] != "parse_error",
                       actual=bundle["status"]),
            GateResult(gate_id="g2", gate_name="files_written",
                       passed=len(applied) > 0,
                       actual=f"{len(applied)} files"),
        ]

        return self._make_result(
            ok=bundle["status"] == "complete" and len(applied) > 0,
            output=output,
            workspace=workspace, t0=t0, tracker=tracker,
            route=route, world_genome_id=world_genome_id,
            worker_genome_id=worker_genome_id, family_id=family_id,
            gates=gates, failure_modes=[],
            applied=applied, git_hash=git_hash,
            bundle=bundle, result=result,
        )

    def _make_result(self, ok, output, workspace, t0, tracker, route,
                      world_genome_id, worker_genome_id, family_id,
                      gates, failure_modes,
                      applied=None, git_hash="", bundle=None, result=None):
        """Build HarnessRun + FailureVector."""
        duration_ms = int((time.time() - t0) * 1000)
        applied = applied or []
        bundle = bundle or {}
        result = result or {}

        run = HarnessRun(
            ok=ok,
            output=output,
            artifacts=[str(Path(workspace) / a) for a in applied],
            model_calls=[{
                "model": route.model,
                "provider": route.provider,
                "reason": route.reason,
                "prompt_tokens": result.get("prompt_tokens", 0),
                "completion_tokens": result.get("completion_tokens", 0),
                "duration_ms": result.get("duration_ms", 0),
                "cost_usd": tracker.total_cost_usd,
            }],
            duration_ms=duration_ms,
            cost_usd=tracker.total_cost_usd,
            total_tokens=tracker.total_tokens,
            metadata={
                "run_id": f"run-{int(t0*1000)}",
                "workspace": workspace,
                "git_hash": git_hash,
                "route_reason": route.reason,
                "model": route.model,
                "usage": tracker.to_dict(),
            },
        )

        fv = run.to_failure_vector(
            world_genome_id=world_genome_id,
            worker_genome_id=worker_genome_id,
            family_id=family_id,
            gates=gates,
            failure_modes=failure_modes,
        )

        return run, fv

    def _git_commit(self, workspace: str, message: str) -> str:
        """Git add + commit in workspace."""
        import subprocess
        try:
            subprocess.run(["git", "init"], cwd=workspace,
                          capture_output=True, timeout=5)
            subprocess.run(["git", "add", "-A"], cwd=workspace,
                          capture_output=True, timeout=5)
            r = subprocess.run(["git", "commit", "-m", message],
                              cwd=workspace, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                h = subprocess.run(["git", "rev-parse", "HEAD"],
                                  cwd=workspace, capture_output=True, text=True, timeout=5)
                return h.stdout.strip() if h.returncode == 0 else ""
        except Exception:
            pass
        return ""
