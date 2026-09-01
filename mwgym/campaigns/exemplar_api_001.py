#!/usr/bin/env python3
"""Exemplar API-001 — the first canonical Moltwork campaign.

One real task type (rate limiter). One deterministic verifier.
One worker version baseline. Training. Reflection. Candidate. Held-out. Report.

Usage:
  python3 mwgym/campaigns/exemplar_api_001.py --phase all
  python3 mwgym/campaigns/exemplar_api_001.py --phase baseline
  python3 mwgym/campaigns/exemplar_api_001.py --phase training --rounds 10
  python3 mwgym/campaigns/exemplar_api_001.py --phase heldout
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path("/root/mwgym")))
sys.path.insert(0, str(Path("/root/workerkit")))

from mwgym.run.spec import WorkerVersion, ComputePolicy
from mwgym.run.executor import execute
from mwgym.run.receipt import receipt_summary, get_campaign_receipts
from mwgym.run.verifier import verify
from mwgym.workspace import LabWorkspace


# ─── Campaign Config ───────────────────────────────────────────────────

CAMPAIGN_ID = "ex-api-001"
TASK_FAMILY = "software.implementation.api_endpoint"
TASK_ID = "rate-limiter"

TASK_INSTRUCTION = """Build a Python class `RateLimiter` that implements a token bucket rate limiter.

Requirements:
- Class name: RateLimiter
- Constructor: __init__(self, rate: float, burst: int)
- Method: allow(self) -> bool — returns True if token available, consumes one
- Method: tokens_remaining(self) -> float — current token count
- Thread-safe (use threading.Lock)
- No external imports (only stdlib)

Write to rate_limiter.py."""

# Held-out task variants
HELDOUT_TASKS = [
    {
        "id": "rate-limiter-burst-test",
        "instruction": """Build a Python class `RateLimiter` implementing a token bucket rate limiter.

Requirements:
- Class: RateLimiter(rate: float, burst: int)
- allow() -> bool: consume one token, return True if available
- tokens_remaining() -> float: current count
- Thread-safe
- No external imports

Write to rate_limiter.py.""",
    },
    {
        "id": "rate-limiter-multi-key",
        "instruction": """Build a Python class `MultiKeyRateLimiter` that rate-limits per key.

Requirements:
- Constructor: __init__(self, rate: float, burst: int)
- allow(self, key: str) -> bool: per-key token bucket
- tokens_remaining(self, key: str) -> float
- Thread-safe
- No external imports

Write to rate_limiter.py (class name: MultiKeyRateLimiter).""",
    },
]

# CGE world seeds for training
WORLD_SEEDS = list(range(1, 21))  # 20 training worlds


# ─── Baseline ──────────────────────────────────────────────────────────

def run_baseline(hydra, lab: LabWorkspace):
    """Run worker v1 baseline on the canonical task."""
    print("\n" + "=" * 60)
    print("PHASE: BASELINE")
    print("=" * 60)

    worker = WorkerVersion(worker_id="worker-api-001", version="v1")
    compute = ComputePolicy(policy_id="bounded", arm="M", budget_usd=0.01, max_requests=1)

    result = execute(
        task_id=TASK_ID,
        task_instruction=TASK_INSTRUCTION,
        task_family=TASK_FAMILY,
        campaign_id=CAMPAIGN_ID,
        opportunity_id="ex-api-001",
        worker=worker,
        compute=compute,
        world_genome_id=f"wg-{TASK_ID}-baseline",
        hydra=hydra,
        lab=lab,
    )

    if result.error:
        print(f"  ERROR: {result.error}")
    else:
        run = result.run
        print(f"  Run: {run.run_id}")
        print(f"  Receipt: {result.receipt_hash}")
        print(f"  Success: {run.evaluation.success}")
        print(f"  Quality: {run.evaluation.quality:.2f}")
        print(f"  Gates:")
        for g in run.evaluation.gates:
            print(f"    {g.gate_id}: {'PASS' if g.passed else 'FAIL'} — {g.actual[:80]}")
        print(f"  Capabilities:")
        for c in run.evaluation.capabilities:
            print(f"    {c.capability}: {c.score:.2f}")
        print(f"  Cost: ${run.actual_cost_usd:.6f}")
        print(f"  Latency: {run.latency_ms}ms")
        print(f"  Git: {run.base_sha[:8]} → {run.final_sha[:8] if run.final_sha else 'none'}")

    return result


# ─── Training ──────────────────────────────────────────────────────────

def run_training(hydra, lab: LabWorkspace, n_rounds: int = 10):
    """Run training rounds with CGE world evolution."""
    print("\n" + "=" * 60)
    print(f"PHASE: TRAINING ({n_rounds} rounds)")
    print("=" * 60)

    worker = WorkerVersion(worker_id="worker-api-001", version="v1")
    compute = ComputePolicy(policy_id="bounded", arm="M", budget_usd=0.01, max_requests=1)

    results = []
    for i in range(n_rounds):
        seed = WORLD_SEEDS[i % len(WORLD_SEEDS)]
        world_id = f"wg-{TASK_ID}-train-{i:03d}"

        print(f"\n  Round {i+1}/{n_rounds} (seed={seed})...", end=" ", flush=True)

        result = execute(
            task_id=TASK_ID,
            task_instruction=TASK_INSTRUCTION,
            task_family=TASK_FAMILY,
            campaign_id=CAMPAIGN_ID,
            worker=worker,
            compute=compute,
            world_genome_id=world_id,
            world_seed=seed,
            hydra=hydra,
            lab=lab,
        )

        if result.error:
            print(f"ERROR: {result.error}")
        else:
            run = result.run
            status = "PASS" if run.evaluation.success else "FAIL"
            print(f"{status} quality={run.evaluation.quality:.2f} ({run.latency_ms}ms)")
            results.append({
                "run_id": run.run_id, "success": run.evaluation.success,
                "quality": run.evaluation.quality, "seed": seed,
                "gates": {g.gate_id: g.passed for g in run.evaluation.gates},
                "failure_modes": run.evaluation.failure_vector.modes,
            })

    # Summary
    passed = sum(1 for r in results if r["success"])
    avg_q = sum(r["quality"] for r in results) / len(results) if results else 0
    print(f"\n  Training: {passed}/{len(results)} passed, avg quality={avg_q:.2f}")

    # Failure mode analysis
    all_modes = {}
    for r in results:
        for m in r.get("failure_modes", []):
            all_modes[m] = all_modes.get(m, 0) + 1
    if all_modes:
        print(f"  Failure modes:")
        for mode, count in sorted(all_modes.items(), key=lambda x: -x[1]):
            print(f"    {mode}: {count}/{len(results)}")

    # Record training summary
    hydra.add_insight(
        insight_id=f"insight-{CAMPAIGN_ID}-training",
        title=f"Training summary: {passed}/{len(results)} passed",
        body=json.dumps({
            "passed": passed, "total": len(results),
            "avg_quality": avg_q, "failure_modes": all_modes,
        }),
        kind="training_summary",
        experiment_id=CAMPAIGN_ID,
        evidence_runs=len(results),
        confidence=avg_q,
    )

    return results


# ─── Held-out ──────────────────────────────────────────────────────────

def run_heldout(hydra, lab: LabWorkspace, context: str = ""):
    """Run both v1 baseline and v2 (with context) on held-out tasks."""
    print("\n" + "=" * 60)
    print("PHASE: HELD-OUT EVALUATION")
    print("=" * 60)

    v1_results = []
    v2_results = []

    for task in HELDOUT_TASKS:
        print(f"\n  {task['id']}:")
        # V1
        r1 = execute(
            task_id=task["id"], task_instruction=task["instruction"],
            task_family=TASK_FAMILY, campaign_id=CAMPAIGN_ID,
            worker=WorkerVersion(worker_id="worker-api-001", version="v1"),
            compute=ComputePolicy(policy_id="bounded", arm="M", budget_usd=0.01, max_requests=1),
            world_genome_id=f"wg-{task['id']}-heldout",
            hydra=hydra, lab=lab,
        )
        s1 = "PASS" if r1.run.evaluation.success else "FAIL"
        print(f"    V1: {s1} quality={r1.run.evaluation.quality:.2f} ({r1.run.latency_ms}ms)")
        v1_results.append({"task": task["id"], "success": r1.run.evaluation.success, "quality": r1.run.evaluation.quality})

        # V2 (with context)
        r2 = execute(
            task_id=task["id"], task_instruction=task["instruction"],
            task_family=TASK_FAMILY, campaign_id=CAMPAIGN_ID,
            worker=WorkerVersion(worker_id="worker-api-001", version="v2"),
            compute=ComputePolicy(policy_id="bounded", arm="M", budget_usd=0.01, max_requests=1),
            world_genome_id=f"wg-{task['id']}-heldout",
            hydra=hydra, lab=lab, context=context,
        )
        s2 = "PASS" if r2.run.evaluation.success else "FAIL"
        print(f"    V2: {s2} quality={r2.run.evaluation.quality:.2f} ({r2.run.latency_ms}ms)")
        v2_results.append({"task": task["id"], "success": r2.run.evaluation.success, "quality": r2.run.evaluation.quality})

    v1_pass = sum(1 for r in v1_results if r["success"])
    v2_pass = sum(1 for r in v2_results if r["success"])
    v1_rate = v1_pass / len(v1_results) if v1_results else 0
    v2_rate = v2_pass / len(v2_results) if v2_results else 0

    print(f"\n  V1: {v1_pass}/{len(v1_results)} ({v1_rate:.0%})")
    print(f"  V2: {v2_pass}/{len(v2_results)} ({v2_rate:.0%})")
    print(f"  Delta: {(v2_rate - v1_rate):+.0%}")
    promoted = v2_rate > v1_rate
    print(f"  PROMOTED: {'YES' if promoted else 'NO'}")

    hydra.add_insight(
        insight_id=f"insight-{CAMPAIGN_ID}-heldout",
        title=f"Held-out: V1={v1_rate:.0%} V2={v2_rate:.0%}",
        body=json.dumps({
            "v1_rate": v1_rate, "v2_rate": v2_rate,
            "delta": v2_rate - v1_rate, "promoted": promoted,
        }),
        kind="heldout_comparison",
        experiment_id=CAMPAIGN_ID,
        evidence_runs=len(v1_results) + len(v2_results),
        confidence=abs(v2_rate - v1_rate),
    )

    return {"v1": v1_results, "v2": v2_results, "promoted": promoted}


# ─── Report ────────────────────────────────────────────────────────────

def print_report(hydra):
    """Print the campaign report."""
    print("\n" + "=" * 60)
    print("CAMPAIGN REPORT")
    print("=" * 60)

    summary = receipt_summary(CAMPAIGN_ID)
    print(f"  Campaign: {summary['campaign_id']}")
    print(f"  Total runs: {summary['total_runs']}")
    print(f"  Passed: {summary['passed']}")
    print(f"  Avg quality: {summary['avg_quality']:.2f}")
    print(f"  Avg cost: ${summary['avg_cost']:.6f}")
    print(f"  Avg latency: {summary['avg_latency_ms']:.0f}ms")

    lab_summary = hydra.summary()
    print(f"\n  Hydra: runs={lab_summary['total_runs']} workers={lab_summary['total_workers']} experiments={lab_summary['total_experiments']}")

    caps = hydra.get_capabilities(f"{CAMPAIGN_ID}/v1")
    if not caps:
        caps = hydra.get_capabilities("worker-api-001/v1")
    print(f"  Capabilities: {len(caps)} rows")
    for c in caps[:10]:
        print(f"    {c['capability']}: {c['mean_score']:.2f} (n={c['n_samples']})")


# ─── Main ──────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="all", choices=["all", "baseline", "training", "heldout", "report"])
    parser.add_argument("--rounds", type=int, default=10)
    args = parser.parse_args()

    hydra = None  # TODO: Wire real HydraDB client
    lab = LabWorkspace()

    if args.phase in ("all", "baseline"):
        run_baseline(hydra, lab)

    if args.phase in ("all", "training"):
        training_results = run_training(hydra, lab, n_rounds=args.rounds)

        # Generate lessons from training
        lessons = []
        all_modes = {}
        for r in training_results:
            for m in r.get("failure_modes", []):
                all_modes[m] = all_modes.get(m, 0) + 1
        for mode, count in all_modes.items():
            if count >= 2:
                lessons.append(f"Common failure: {mode} — explicitly handle this case.")
        lessons.append("Always handle edge cases: empty inputs, boundary conditions, thread safety.")
        lessons.append("Use only stdlib imports. No external dependencies.")

        context = "\n".join(f"- {l}" for l in lessons)

        if args.phase in ("all", "heldout"):
            run_heldout(hydra, lab, context=context)

    if args.phase in ("all", "report"):
        print_report(hydra)


if __name__ == "__main__":
    main()
