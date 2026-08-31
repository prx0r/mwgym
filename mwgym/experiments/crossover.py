"""Crossover experiment — harness comparison on filesystem tasks."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..schema.genome import WorkerGenome
from ..harnesses.direct import DirectAdapter
from ..harnesses.fast import FastExecutor


# Deterministic filesystem tasks — check against output content
TASKS = [
    {"id": "fs-01", "task": "Write the word HELLO", "check": "HELLO"},
    {"id": "fs-02", "task": "Write the number 42", "check": "42"},
    {"id": "fs-03", "task": "Write JSON: {\"key\": \"value\"}", "check": "key"},
    {"id": "fs-04", "task": "Write a list: item1, item2, item3", "check": "item1"},
    {"id": "fs-05", "task": "Write YAML: name: test", "check": "name: test"},
    {"id": "fs-06", "task": "Write a markdown heading: # Notes", "check": "# Notes"},
    {"id": "fs-07", "task": "Write Python code: print('hi')", "check": "print"},
    {"id": "fs-08", "task": "Write text: Project README", "check": "Project README"},
    {"id": "fs-09", "task": "Write the word Done", "check": "Done"},
    {"id": "fs-10", "task": "Write the word COMPLETE", "check": "COMPLETE"},
]


class CrossoverExperiment:
    """Run harness crossover experiment."""

    def __init__(self, workspace: str = "/tmp/mwgym-experiments"):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.direct = DirectAdapter()
        self.fast = FastExecutor()
        self.results: list[dict] = []

    async def run_task(self, genome: WorkerGenome, task: dict, run_id: str) -> dict:
        """Run one task with one genome."""
        task_dir = self.workspace / f"{genome.id}-{task['id']}"
        task_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.time()

        if genome.harness_kind == "direct":
            instance = await self.direct.provision(genome, f"worker-{run_id}")
            result = await self.direct.run(instance, task["task"], str(task_dir))
        elif genome.harness_kind == "fast":
            instance = await self.fast.provision(genome, f"worker-{run_id}")
            result = await self.fast.run(instance, task["task"], str(task_dir))
        else:
            return {"ok": False, "error": f"unknown harness: {genome.harness_kind}"}

        # Check if output contains expected text
        output_lower = result.output.lower()
        check_lower = task["check"].lower()
        success = check_lower in output_lower

        return {
            "run_id": run_id,
            "genome_id": genome.id,
            "harness": genome.harness_kind,
            "task_id": task["id"],
            "success": success,
            "model_calls": len(result.model_calls),
            "total_tokens": result.total_tokens,
            "duration_ms": result.duration_ms,
            "cost_usd": result.cost_usd,
            "output_preview": result.output[:100],
        }

    async def run_experiment(self, n_tasks: int = 5) -> dict:
        """Run genomes on tasks."""
        genomes = [
            WorkerGenome.direct_fast(),
        ]

        tasks = TASKS[:n_tasks]
        results = []

        for genome in genomes:
            for i, task in enumerate(tasks):
                run_id = f"{genome.id}-{task['id']}"
                r = await self.run_task(genome, task, run_id)
                results.append(r)
                print(f"  {r['genome_id']} {r['task_id']}: success={r['success']} tokens={r['total_tokens']} ms={r['duration_ms']}")

        self.results = results

        # Aggregate
        summary = {}
        for genome in genomes:
            genome_results = [r for r in results if r["genome_id"] == genome.id]
            if not genome_results:
                continue
            summary[genome.id] = {
                "n": len(genome_results),
                "success_rate": sum(1 for r in genome_results if r["success"]) / len(genome_results),
                "avg_model_calls": sum(r["model_calls"] for r in genome_results) / len(genome_results),
                "avg_tokens": sum(r["total_tokens"] for r in genome_results) / len(genome_results),
                "avg_duration_ms": sum(r["duration_ms"] for r in genome_results) / len(genome_results),
                "total_cost_usd": sum(r["cost_usd"] for r in genome_results),
            }

        return {"results": results, "summary": summary}
