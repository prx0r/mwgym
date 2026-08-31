"""Crossover Benchmark — when is Letta worth the cost?

Same 100 simple tasks, 4 arms:
- A: direct model, one shot
- B: Letta stateless
- C: Letta stateful
- D: dynamic router

Measure: success, model calls, tokens, latency, cost
"""
from __future__ import annotations

import time
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mwgym.core.model_call import ModelCall, RuntimeProfile
from mwgym.core.budget_ledger import BudgetLedger


# Simple tasks for calibration
SIMPLE_TASKS = [
    {"id": "t1", "task": "Create file result.txt with content: HELLO", "check": "HELLO"},
    {"id": "t2", "task": "Create file output.txt with content: 42", "check": "42"},
    {"id": "t3", "task": "Create file data.json with content: {\"key\": \"value\"}", "check": '"key"'},
    {"id": "t4", "task": "Create file list.txt with content: item1\nitem2\nitem3", "check": "item1"},
    {"id": "t5", "task": "Create file config.yaml with content: name: test", "check": "name: test"},
    {"id": "t6", "task": "Create file notes.md with content: # Notes\nImportant", "check": "# Notes"},
    {"id": "t7", "task": "Create file script.py with content: print('hi')", "check": "print"},
    {"id": "t8", "task": "Create file readme.txt with content: Project README", "check": "Project README"},
    {"id": "t9", "task": "Create file summary.txt with content: Done", "check": "Done"},
    {"id": "t10", "task": "Create file final.txt with content: COMPLETE", "check": "COMPLETE"},
]


@dataclass
class BenchmarkResult:
    arm: str = ""
    task_id: str = ""
    success: bool = False
    model_calls: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    cost_usd: float = 0.0
    runtime: str = ""
    error: str = ""


class CrossoverBenchmark:
    def __init__(self, workspace: str = "/tmp/mwgym-benchmark"):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.results: list[dict] = []

    def run_arm(self, arm: str, profile: RuntimeProfile, task: dict, executor: Any) -> BenchmarkResult:
        """Run one task with one runtime profile."""
        t0 = time.time()
        task_dir = self.workspace / f"{arm}-{task['id']}"
        task_dir.mkdir(parents=True, exist_ok=True)

        try:
            result = executor.run(
                task=task["task"],
                workspace=str(task_dir),
                profile=profile,
            )

            # Check if file was created with correct content
            expected_file = task_dir / "result.txt"
            success = False
            if expected_file.exists():
                content = expected_file.read_text()
                success = task["check"] in content

            duration = (time.time() - t0) * 1000

            return BenchmarkResult(
                arm=arm, task_id=task["id"], success=success,
                model_calls=result.get("model_calls", 1),
                total_tokens=result.get("total_tokens", 0),
                duration_ms=duration,
                cost_usd=result.get("cost_usd", 0.0),
                runtime=profile.runtime,
            )
        except Exception as e:
            return BenchmarkResult(
                arm=arm, task_id=task["id"], success=False,
                error=str(e), runtime=profile.runtime,
            )

    def run_benchmark(self, executor: Any, n_tasks: int = 10) -> dict:
        """Run all arms on all tasks."""
        arms = {
            "A-direct": RuntimeProfile.direct(),
            "B-letta-stateless": RuntimeProfile.letta_stateless(),
            "C-letta-stateful": RuntimeProfile.letta_stateful(),
        }

        tasks = SIMPLE_TASKS[:n_tasks]
        results = []

        for arm_name, profile in arms.items():
            for task in tasks:
                r = self.run_arm(arm_name, profile, task, executor)
                results.append(r.__dict__)

        self.results = results

        # Aggregate
        summary = {}
        for arm_name in arms:
            arm_results = [r for r in results if r["arm"] == arm_name]
            if not arm_results:
                continue
            summary[arm_name] = {
                "n": len(arm_results),
                "success_rate": sum(1 for r in arm_results if r["success"]) / len(arm_results),
                "avg_model_calls": sum(r["model_calls"] for r in arm_results) / len(arm_results),
                "avg_tokens": sum(r["total_tokens"] for r in arm_results) / len(arm_results),
                "avg_duration_ms": sum(r["duration_ms"] for r in arm_results) / len(arm_results),
                "total_cost_usd": sum(r["cost_usd"] for r in arm_results),
                "cost_per_success": sum(r["cost_usd"] for r in arm_results) / max(1, sum(1 for r in arm_results if r["success"])),
            }

        return summary
