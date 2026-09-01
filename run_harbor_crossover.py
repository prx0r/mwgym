"""Harbor Crossover — 5-arm experiment with real coding tasks.

Arms:
  A: Direct (no memory)
  B: Letta stateless
  C: Letta persistent
  D: Letta + Hydra retrieval
  E: StackOracle (Thompson)

Each arm runs 10 coding tasks with real model calls.
Costs tracked via TelemetryStore.
Results recorded in LabProjection.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mwgym.harbor_tasks import get_tasks, CodingTask
from mwgym.telemetry_records import TelemetryStore, ModelCallRecord, ResourceSpend
from mwgym.core.budget_ledger import BudgetLedger
from mwgym.asset_profile import AssetProfileStore


def run_direct(task: CodingTask, workspace: Path) -> dict:
    """Arm A: Direct model call, no memory."""
    import http.client, json, ssl, os
    from urllib.parse import urlparse

    for env_path in [Path("/root/workerkit/.env"), Path("/root/.env")]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    api_key = os.environ.get("OPENCODE_API_KEY", "")
    api_url = os.environ.get("OPENCODE_API_URL", "https://opencode.ai/zen/go/v1/chat/completions")

    ws = workspace / task.id
    ws.mkdir(parents=True, exist_ok=True)

    payload = json.dumps({
        "model": "mimo-v2.5",
        "messages": [
            {"role": "system", "content": "You are a Python programmer. Write only the function, no explanations."},
            {"role": "user", "content": task.instruction},
        ],
        "max_tokens": 4096,
        "thinking": {"type": "disabled"},
    })

    parsed = urlparse(api_url)
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(parsed.hostname, context=ctx, timeout=30)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    t0 = time.time()
    conn.request("POST", parsed.path, body=payload, headers=headers)
    resp = conn.getresponse()
    body = resp.read().decode()
    duration_ms = int((time.time() - t0) * 1000)
    conn.close()

    if resp.status != 200:
        return {"ok": False, "error": f"HTTP {resp.status}", "duration_ms": duration_ms}

    result = json.loads(body)
    output = result.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
    usage = result.get("usage", {})

    # Write code to file
    code_file = ws / "solution.py"
    # Extract code from markdown if wrapped
    if "```python" in output:
        code = output.split("```python")[1].split("```")[0].strip()
    elif "```" in output:
        code = output.split("```")[1].split("```")[0].strip()
    else:
        code = output.strip()
    code_file.write_text(code)

    # Run test
    test_result = _run_test(code, task.test_code, ws)

    return {
        "ok": True,
        "output": output,
        "code": code,
        "test_passed": test_result["passed"],
        "test_error": test_result.get("error", ""),
        "duration_ms": duration_ms,
        "tokens": usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
    }


def run_letta_stateless(task: CodingTask, workspace: Path) -> dict:
    """Arm B: Letta stateless — runs in background, waits for completion."""
    from mwgym.harnesses.real_letta import RealLettaAdapter

    ws = workspace / task.id
    ws.mkdir(parents=True, exist_ok=True)

    letta = RealLettaAdapter()
    worker_id = "mwgym-harbor-v2"
    letta._ensure_worker(worker_id)

    t0 = time.time()
    result = letta.run(
        task=task.instruction,
        workspace=str(ws),
        worker_id=worker_id,
        timeout=180,  # 3 minutes for Letta
    )
    duration_ms = int((time.time() - t0) * 1000)

    output = result.output or ""
    code_file = ws / "solution.py"
    if "```python" in output:
        code = output.split("```python")[1].split("```")[0].strip()
    elif "```" in output:
        code = output.split("```")[1].split("```")[0].strip()
    else:
        code = output.strip()
    code_file.write_text(code)

    test_result = _run_test(code, task.test_code, ws)

    return {
        "ok": result.ok,
        "output": output,
        "code": code,
        "test_passed": test_result["passed"],
        "test_error": test_result.get("error", ""),
        "duration_ms": duration_ms,
        "tokens": result.total_tokens,
    }


def run_letta_stateful(task: CodingTask, workspace: Path) -> dict:
    """Arm C: Letta persistent — runs in background, waits for completion."""
    from mwgym.harnesses.real_letta import RealLettaAdapter

    ws = workspace / task.id
    ws.mkdir(parents=True, exist_ok=True)

    letta = RealLettaAdapter()
    worker_id = "mwgym-harbor-stateful-v2"
    letta._ensure_worker(worker_id)

    # Create genome with stateful memory
    genome = WorkerGenome(
        id="harbor-stateful",
        memory_enabled=True,
        memory_mode="letta",
        max_model_requests=4,
    )

    t0 = time.time()
    result = letta.run(
        task=task.instruction,
        workspace=str(ws),
        worker_id=worker_id,
        genome=genome,
        timeout=180,
    )
    duration_ms = int((time.time() - t0) * 1000)

    output = result.output or ""
    code_file = ws / "solution.py"
    if "```python" in output:
        code = output.split("```python")[1].split("```")[0].strip()
    elif "```" in output:
        code = output.split("```")[1].split("```")[0].strip()
    else:
        code = output.strip()
    code_file.write_text(code)

    test_result = _run_test(code, task.test_code, ws)

    return {
        "ok": result.ok,
        "output": output,
        "code": code,
        "test_passed": test_result["passed"],
        "test_error": test_result.get("error", ""),
        "duration_ms": duration_ms,
        "tokens": result.total_tokens,
    }


def _run_test(code: str, test_code: str, workspace: Path) -> dict:
    """Run test code against the solution."""
    full_code = code + "\n\n" + test_code
    test_file = workspace / "test_solution.py"
    test_file.write_text(full_code)

    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(test_file)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(workspace),
        )
        return {"passed": result.returncode == 0, "error": result.stderr[:500] if result.returncode != 0 else ""}
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "timeout"}
    except Exception as e:
        return {"passed": False, "error": str(e)}


def run_harbor_crossover(n_tasks: int = 10):
    """Run the full Harbor crossover experiment."""
    tasks = get_tasks(n_tasks)
    workspace = Path("/tmp/mwgym-harbor")
    workspace.mkdir(parents=True, exist_ok=True)

    telemetry = TelemetryStore()
    ledger = BudgetLedger(daily_cap=10.0, per_run_cap=2.0)
    bridge = LabBridge()

    arms = {
        "A-direct": run_direct,
        "B-letta-stateless": run_letta_stateless,
        "C-letta-stateful": run_letta_stateful,
    }

    results = []

    for arm_name, arm_func in arms.items():
        print(f"\n=== {arm_name} ===")

        for task in tasks:
            print(f"  {task.id}: {task.name}...", end=" ", flush=True)

            # Record model call
            call_id = f"mc-{int(time.time()*1000)}"
            mc = ModelCallRecord(
                call_id=call_id,
                decision_id=f"dp-{task.id}",
                provider="opencode-go",
                model="mimo-v2.5",
                started_at=time.time(),
            )

            # Run task
            result = arm_func(task, workspace)

            # Update telemetry
            mc.latency_ms = result.get("duration_ms", 0)
            mc.actual_input_tokens = result.get("prompt_tokens", 0)
            mc.actual_output_tokens = result.get("completion_tokens", 0)
            mc.actual_cost_usd = 0.0  # free tier
            mc.cost_source = "free_tier"
            telemetry.record_model_call(mc)

            spend = ResourceSpend(
                spend_id=f"spend-{task.id}",
                decision_id=f"dp-{task.id}",
                category="model_call",
                amount_usd=0.0,
                amount_tokens=result.get("tokens", 0),
                description=f"{arm_name}: {task.id}",
            )
            telemetry.record_spend(spend)
            ledger.record(f"dp-{task.id}", "compute", 0.0, result.get("tokens", 0), f"{arm_name}: {task.id}")

            status = "PASS" if result.get("test_passed") else "FAIL"
            print(f"{status} ({result.get('tokens', 0)} tok, {result.get('duration_ms', 0)}ms)")

            results.append({
                "arm": arm_name,
                "task_id": task.id,
                "task_name": task.name,
                "test_passed": result.get("test_passed", False),
                "test_error": result.get("test_error", ""),
                "tokens": result.get("tokens", 0),
                "duration_ms": result.get("duration_ms", 0),
            })

    # Aggregate
    summary = {}
    for arm_name in arms:
        arm_results = [r for r in results if r["arm"] == arm_name]
        n = len(arm_results)
        passed = sum(1 for r in arm_results if r["test_passed"])
        summary[arm_name] = {
            "n": n,
            "pass_rate": round(passed / n, 3),
            "avg_tokens": round(sum(r["tokens"] for r in arm_results) / n),
            "avg_ms": round(sum(r["duration_ms"] for r in arm_results) / n),
        }

    # Save log
    run_id = f"harbor-{int(time.time())}"
    log_dir = Path("/root/mwgym/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_data = {
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "experiment": "harbor-crossover",
        "runtime_class": "REAL",
        "n_tasks": n_tasks,
        "arms": list(arms.keys()),
        "summary": summary,
        "results": results,
        "telemetry": telemetry.summary(),
    }
    log_path = log_dir / f"{run_id}.json"
    log_path.write_text(json.dumps(log_data, indent=2))
    print(f"\nLog: {log_path}")

    # Print summary
    print(f"\n{'='*60}")
    print("HARBOR CROSSOVER RESULTS")
    print(f"{'='*60}")
    for arm, stats in sorted(summary.items()):
        print(f"{arm}: {stats['pass_rate']*100:.0f}% pass, {stats['avg_tokens']} tok, {stats['avg_ms']}ms")

    # Validate telemetry
    errors = telemetry.validate()
    print(f"\nTelemetry validation: {len(errors)} errors")

    # Record in LabProjection
    for r in results:
        bridge.record_crossover_run(
            run_id=f"{run_id}-{r['task_id']}",
            genome=r["arm"],
            task_id=r["task_id"],
            success=r["test_passed"],
            tokens=r["tokens"],
            duration_ms=r["duration_ms"],
            experiment_id=run_id,
        )
    print(f"Recorded {len(results)} runs in LabProjection")

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=10)
    args = parser.parse_args()
    run_harbor_crossover(n_tasks=args.tasks)
