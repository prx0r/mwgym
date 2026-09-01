"""Executor — the single owner of one WorkerRun lifecycle.

One WorkerRun = one call to execute(). Everything else is a projection.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .spec import (
    WorkerRun, WorkerVersion, ComputePolicy, ProviderRequest,
    Evaluation, GateResult, CapabilityScore, FailureVector,
)
from .verifier import verify
from .receipt import record_receipt

sys.path.insert(0, str(Path("/root/mwgym")))
sys.path.insert(0, str(Path("/root/workerkit")))

from mwgym.harnesses.pydantic_bats import PydanticBATSHarness, UsageLimits
from mwgym.workspace import LabWorkspace


@dataclass
class ExecuteResult:
    """Result of executing one WorkerRun."""
    run: WorkerRun
    receipt_hash: str
    hydra_written: bool
    error: str = ""


def execute(
    *,
    task_id: str,
    task_instruction: str,
    task_family: str,
    campaign_id: str,
    opportunity_id: str = "",
    worker: WorkerVersion | None = None,
    compute: ComputePolicy | None = None,
    world_genome_id: str = "",
    world_seed: int = 0,
    evaluator_version: str = "v1",
    verify_code: str = "",
    hydra=None,
    lab: LabWorkspace | None = None,
    context: str = "",
    estimated_value_usd: float = 0.0,
) -> ExecuteResult:
    """Execute one canonical WorkerRun.

    Orchestrator owns the entire lifecycle:
      1. Create Git worktree
      2. Seed world (B0)
      3. Run harness
      4. Verify output
      5. Record receipt
      6. Project to Hydra
      7. Commit worker output (B1)
    """
    worker = worker or WorkerVersion(worker_id="default", version="v1")
    compute = compute or ComputePolicy(arm="M", budget_usd=0.05)
    hydra = hydra or None  # TODO: Wire real HydraDB client
    lab = lab or LabWorkspace()

    run = WorkerRun(
        campaign_id=campaign_id,
        opportunity_id=opportunity_id,
        task_family=task_family,
        task_fixture_id=task_id,
        estimated_value_usd=estimated_value_usd,
        worker=worker,
        world_genome_id=world_genome_id,
        world_seed=world_seed,
        evaluator_version=evaluator_version,
        compute=compute,
    )

    t0 = time.time()

    try:
        # Step 1: Git worktree
        run_id_safe = run.run_id.replace("wk_", "run-")
        wt = lab.create_run(run_id_safe)

        # Step 2: Seed world files (B0)
        task_file = {"task.md": f"# {task_id}\n\n{task_instruction}"}
        wt.seed_world(task_file, f"world: {task_id}")
        run.base_sha = wt.base_commit

        # Step 3: Execute via PydanticBATS
        harness = PydanticBATSHarness()
        limits = UsageLimits(
            request_limit=compute.max_requests,
            cost_limit_usd=compute.budget_usd,
            wall_time_limit_s=30,
        )

        task_msg = task_instruction
        if context:
            task_msg = f"Context from prior experience:\n{context}\n\n{task_instruction}"

        run_obj, fv_harness = harness.run(
            task=task_msg,
            workspace=wt.path,
            limits=limits,
            world_genome_id=world_genome_id,
            worker_genome_id=f"{worker.worker_id}/{worker.version}",
            family_id=task_family,
        )

        # Record provider requests
        for mc in run_obj.model_calls:
            run.provider_requests.append(ProviderRequest(
                model=mc.get("model", ""),
                provider=mc.get("provider", ""),
                input_tokens=mc.get("prompt_tokens", 0),
                output_tokens=mc.get("completion_tokens", 0),
                latency_ms=mc.get("duration_ms", 0),
                cash_cost_usd=mc.get("cost_usd", 0),
                reason=mc.get("reason", ""),
            ))

        run.actual_cost_usd = run_obj.cost_usd

        # Step 4: Deterministic verification
        evaluation = verify(wt.path, task_id, verify_code)
        run.evaluation = evaluation

        # Step 5: Git commit worker output (B1)
        wt.commit_worker_output(f"worker ({worker.worker_id}/{worker.version}): {'PASS' if evaluation.success else 'FAIL'}")
        run.final_sha = wt.final_commit
        run.changed_files = wt.files_changed()

        # Diff hash
        diff = wt.diff()
        import hashlib
        run.diff_sha = hashlib.sha256(diff.encode()).hexdigest()[:16] if diff else ""

        # Step 6: Record receipt (append-only)
        receipt_hash = record_receipt(run)

        # Step 7: Project to Hydra
        from mwgym.schema.world import FailureVector as FV
        hydra_record = run.to_hydra_record()
        fv_dict = hydra_record.pop("failure_vector", {})
        fv_obj = FV(
            run_id=run.run_id,
            world_genome_id=run.world_genome_id,
            worker_genome_id=f"{worker.worker_id}/{worker.version}",
            failure_modes=tuple(fv_dict.get("modes", [])),
            quality_score=run.evaluation.quality,
            correctness=run.evaluation.correctness,
            completeness=run.evaluation.completeness,
        )
        hydra.record_run(**hydra_record, failure_vector=fv_obj)
        hydra.record_capability(
            f"{worker.worker_id}/{worker.version}", task_family,
            "code.write", evaluation.correctness,
        )
        hydra.add_node(f"run:{run.run_id}", "Run", {
            "campaign": campaign_id, "task": task_id,
            "success": evaluation.success, "quality": evaluation.quality,
        })
        hydra.add_node(f"worker:{worker.worker_id}/{worker.version}", "WorkerVersion", {
            "worker_id": worker.worker_id, "version": worker.version,
        })
        hydra.add_edge(f"run:{run.run_id}", f"worker:{worker.worker_id}/{worker.version}", "EXECUTED_BY")

        for gate in evaluation.gates:
            gate_node = f"gate:{run.run_id}:{gate.gate_id}"
            hydra.add_node(gate_node, "GateResult", {
                "gate_id": gate.gate_id, "passed": gate.passed,
            })
            hydra.add_edge(f"run:{run.run_id}", gate_node, "EVALUATED_BY")

        # Record trajectory
        traj_events = []
        for pr in run.provider_requests:
            traj_events.append({
                "step_type": "model_call",
                "model": pr.model,
                "input_tokens": pr.input_tokens,
                "output_tokens": pr.output_tokens,
                "duration_ms": pr.latency_ms,
                "reason": pr.reason,
            })
        conn = hydra._conn()
        conn.execute("""
            INSERT OR REPLACE INTO trajectories (run_id, events, created_at)
            VALUES (?, ?, ?)
        """, (run.run_id, json.dumps(traj_events), time.time()))
        conn.commit()
        conn.close()

        run.latency_ms = int((time.time() - t0) * 1000)
        run.receipt_hash = receipt_hash

        return ExecuteResult(run=run, receipt_hash=receipt_hash, hydra_written=True)

    except Exception as e:
        run.latency_ms = int((time.time() - t0) * 1000)
        return ExecuteResult(run=run, receipt_hash="", hydra_written=False, error=str(e))
