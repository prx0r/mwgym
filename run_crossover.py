"""Full crossover experiment — 4 arms including dynamic router.

Arms:
  A: direct-fast (one-shot, no artifacts)
  B: fast-bundle (ActionBundle, produces files)
  C: [reserved for letta-stateless]
  D: dynamic-router (picks A or B per task)

Runs all arms on the same tasks, logs results, calls review.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mwgym.schema.genome import WorkerGenome
from mwgym.harnesses.direct import DirectAdapter
from mwgym.harnesses.fast import FastExecutor
from mwgym.harnesses.letta import LettaAdapter
from mwgym.harnesses.router import DynamicRouter
from mwgym.harnesses.base import HarnessInstance


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


async def run_direct(direct: DirectAdapter, genome: WorkerGenome, task: dict,
                     workspace: Path, run_id: str) -> dict:
    """Run one task with direct-fast genome."""
    task_dir = workspace / f"{genome.id}-{task['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)

    instance = await direct.provision(genome, f"direct-{run_id}")
    t0 = time.time()
    result = await direct.run(instance, task["task"], str(task_dir))
    duration_ms = int((time.time() - t0) * 1000)

    # Check success by looking at output
    success = task["check"].lower() in result.output.lower() if result.output else False

    return {
        "genome": genome.id,
        "task_id": task["id"],
        "task": task["task"],
        "success": success,
        "model_calls": len(result.model_calls),
        "tokens": result.total_tokens,
        "ms": duration_ms,
        "cost": result.cost_usd,
        "artifacts": result.artifacts,
        "output_preview": result.output[:120] if result.output else "",
    }


async def run_fast(fast: FastExecutor, task: dict,
                   workspace: Path, run_id: str) -> dict:
    """Run one task with fast-bundle genome."""
    task_dir = workspace / f"fast-bundle-{task['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)

    instance = HarnessInstance(harness="fast", worker_id=f"fast-{run_id}")
    t0 = time.time()
    result = fast.run(instance, task["task"], str(task_dir))
    duration_ms = int((time.time() - t0) * 1000)

    # Check success
    success = False
    if result.ok and result.output:
        # Check output or artifacts
        if task["check"].lower() in result.output.lower():
            success = True
        else:
            # Check artifact files
            for artifact_path in result.artifacts:
                p = Path(artifact_path)
                if p.exists() and task["check"].lower() in p.read_text().lower():
                    success = True
                    break

    return {
        "genome": "fast-bundle",
        "task_id": task["id"],
        "task": task["task"],
        "success": success,
        "model_calls": len(result.model_calls),
        "tokens": result.total_tokens,
        "ms": duration_ms,
        "cost": result.cost_usd,
        "artifacts": result.artifacts,
        "output_preview": result.output[:120] if result.output else "",
    }


async def run_router(router: DynamicRouter, task: dict,
                     workspace: Path, run_id: str) -> dict:
    """Run one task with the dynamic router."""
    task_dir = workspace / f"router-{task['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    result = await router.run(task["task"], str(task_dir), run_id=run_id)
    duration_ms = int((time.time() - t0) * 1000)

    # Check success
    success = False
    output = result.get("output", "")
    if output and task["check"].lower() in output.lower():
        success = True
    else:
        for artifact_path in result.get("artifacts", []):
            p = Path(artifact_path)
            if p.exists() and task["check"].lower() in p.read_text().lower():
                success = True
                break

    return {
        "genome": "D-router",
        "task_id": task["id"],
        "task": task["task"],
        "success": success,
        "model_calls": result.get("model_calls", 0),
        "tokens": result.get("total_tokens", 0),
        "ms": duration_ms,
        "cost": result.get("cost_usd", 0.0),
        "artifacts": result.get("artifacts", []),
        "output_preview": output[:120] if output else "",
        "routed_to": result.get("routed_to", ""),
        "route_reason": result.get("reason", ""),
    }


async def main():
    workspace = Path("/tmp/mwgym-exp/crossover-v2")
    workspace.mkdir(parents=True, exist_ok=True)

    run_id = f"cross-{int(time.time())}"
    log_dir = Path("/root/mwgym/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    from mwgym.core.budget_ledger import BudgetLedger
    ledger = BudgetLedger(daily_cap=10.0, per_run_cap=2.0)

    direct = DirectAdapter()
    fast = FastExecutor()
    letta = LettaAdapter()
    router = DynamicRouter()

    results = []

    # Arm A: direct-fast
    print("=== Arm A: direct-fast ===")
    genome_a = WorkerGenome.direct_fast()
    for task in TASKS:
        r = await run_direct(direct, genome_a, task, workspace, run_id)
        results.append(r)
        ledger.record(f"{run_id}-{r['task_id']}", "compute", 0.0, r["tokens"],
                      f"direct-fast: {r['task_id']}")
        status = "PASS" if r["success"] else "FAIL"
        print(f"  {r['task_id']}: {status} ({r['tokens']} tok, {r['ms']}ms)")

    # Arm B: fast-bundle
    print("\n=== Arm B: fast-bundle ===")
    for task in TASKS:
        r = await run_fast(fast, task, workspace, run_id)
        results.append(r)
        ledger.record(f"{run_id}-{r['task_id']}", "compute", 0.0, r["tokens"],
                      f"fast-bundle: {r['task_id']}")
        status = "PASS" if r["success"] else "FAIL"
        print(f"  {r['task_id']}: {status} ({r['tokens']} tok, {r['ms']}ms)")

    # Arm C: letta-stateless
    print("\n=== Arm C: letta-stateless ===")
    for task in TASKS:
        task_dir = workspace / f"letta-stateless-{task['id']}"
        task_dir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        result = letta.run_stateless(task["task"], str(task_dir), worker_id=f"letta-{run_id}")
        duration_ms = int((time.time() - t0) * 1000)
        # Check success
        success = False
        if result.output and task["check"].lower() in result.output.lower():
            success = True
        else:
            for artifact_path in result.artifacts:
                p = Path(artifact_path)
                if p.exists() and task["check"].lower() in p.read_text().lower():
                    success = True
                    break
        r = {
            "genome": "C-letta-stateless",
            "task_id": task["id"],
            "task": task["task"],
            "success": success,
            "model_calls": len(result.model_calls),
            "tokens": result.total_tokens,
            "ms": result.duration_ms,
            "cost": result.cost_usd,
            "artifacts": result.artifacts,
            "output_preview": result.output[:120] if result.output else "",
        }
        results.append(r)
        ledger.record(f"{run_id}-{r['task_id']}", "compute", 0.0, r["tokens"],
                      f"letta-stateless: {r['task_id']}")
        status = "PASS" if r["success"] else "FAIL"
        print(f"  {r['task_id']}: {status} ({r['tokens']} tok, {r['ms']}ms)")

    # Arm D: dynamic router
    print("\n=== Arm D: dynamic router ===")
    for task in TASKS:
        r = await run_router(router, task, workspace, run_id)
        results.append(r)
        ledger.record(f"{run_id}-{r['task_id']}", "compute", 0.0, r["tokens"],
                      f"D-router→{r.get('routed_to','?')}: {r['task_id']}")
        status = "PASS" if r["success"] else "FAIL"
        routed = r.get("routed_to", "?")
        print(f"  {r['task_id']}: {status} (routed→{routed}, {r['tokens']} tok, {r['ms']}ms)")

    # Aggregate
    summary = {}
    for genome_name in ["direct-fast", "fast-bundle", "C-letta-stateless", "D-router"]:
        genome_results = [r for r in results if r["genome"] == genome_name]
        if not genome_results:
            continue
        n = len(genome_results)
        successes = sum(1 for r in genome_results if r["success"])
        summary[genome_name] = {
            "n": n,
            "pass_rate": round(successes / n, 3),
            "total_tokens": sum(r["tokens"] for r in genome_results),
            "avg_tokens": round(sum(r["tokens"] for r in genome_results) / n),
            "avg_ms": round(sum(r["ms"] for r in genome_results) / n),
            "total_artifacts": sum(len(r.get("artifacts", [])) for r in genome_results),
        }

    # Budget summary
    budget_summary = {
        "total_spent_usd": ledger.total_spent(),
        "by_category": ledger.by_category(),
        "remaining": ledger.remaining(),
        "total_entries": len(ledger.entries),
    }

    # Router routing decisions
    router_decisions = [r for r in results if r["genome"] == "D-router"]
    routing_summary = {}
    for r in router_decisions:
        routed_to = r.get("routed_to", "unknown")
        routing_summary[routed_to] = routing_summary.get(routed_to, 0) + 1

    # Log
    log_data = {
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "experiment": "crossover-v2-direct-fast-router",
        "tasks": len(TASKS),
        "genomes": ["direct-fast", "fast-bundle", "C-letta-stateless", "D-router"],
        "results": results,
        "summary": summary,
        "budget": budget_summary,
        "router_routing": routing_summary,
        "router_decisions": router.decisions,
    }

    log_path = log_dir / f"{run_id}.json"
    log_path.write_text(json.dumps(log_data, indent=2))
    print(f"\nLog: {log_path}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for genome, s in sorted(summary.items()):
        print(f"  {genome}: {s['pass_rate']*100:.0f}% pass, {s['avg_tokens']} avg tok, {s['avg_ms']}ms avg, {s['total_artifacts']} artifacts")
    print(f"\nRouter routing: {routing_summary}")
    print(f"\nBudget: {budget_summary['total_entries']} entries, ${budget_summary['total_spent_usd']:.4f} total")
    print(f"  Remaining: ${budget_summary['remaining']['per_run']:.4f} per run, ${budget_summary['remaining']['daily']:.4f} daily")

    # Run review
    import subprocess
    subprocess.run(["python3", "/root/mwgym/review.py"], check=False)


if __name__ == "__main__":
    asyncio.run(main())
