"""WorkerRun — the canonical execution record for Moltwork.

Every worker execution produces exactly one WorkerRun. It is append-only
and content-addressed. Everything else consumes or produces something around it.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


def _uid() -> str:
    return f"wk_{uuid.uuid4().hex[:12]}"


def _sha256(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


@dataclass
class ProviderRequest:
    """One model/provider call within a run."""
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cash_cost_usd: float = 0.0
    free_quota_used: bool = False
    reason: str = ""


@dataclass
class GateResult:
    """One deterministic gate check."""
    gate_id: str = ""
    gate_name: str = ""
    passed: bool = False
    actual: str = ""
    expected: str = ""
    severity: str = "error"  # error | warning


@dataclass
class CapabilityScore:
    """Score for one capability dimension."""
    capability: str = ""
    score: float = 0.0
    evidence: str = ""


@dataclass
class FailureVector:
    """What went wrong in a run."""
    modes: list[str] = field(default_factory=list)
    severity: float = 0.0  # 0=perfect, 1=fatal


@dataclass
class Evaluation:
    """Complete evaluation of a run."""
    success: bool = False
    quality: float = 0.0
    correctness: float = 0.0
    completeness: float = 0.0
    gates: list[GateResult] = field(default_factory=list)
    capabilities: list[CapabilityScore] = field(default_factory=list)
    failure_vector: FailureVector = field(default_factory=FailureVector)


@dataclass
class WorkerVersion:
    """A versioned worker identity."""
    worker_id: str = ""
    version: str = "v1"
    parent_version: str = ""
    letta_agent_id: str = ""
    memfs_commit: str = ""
    skills_commit: str = ""
    process_version: str = "default"
    created_at: float = field(default_factory=time.time)


@dataclass
class ComputePolicy:
    """What resources to spend."""
    policy_id: str = ""
    arm: str = "M"  # F=free, M=moltwork, Q=quality
    budget_usd: float = 0.05
    max_requests: int = 3
    model_preference: str = ""


@dataclass
class WorkerRun:
    """The canonical execution record.

    One worker execution = one WorkerRun. Append-only.
    Everything else is a projection or derivation.
    """
    run_id: str = field(default_factory=_uid)
    campaign_id: str = ""

    # Work
    opportunity_id: str = ""
    work_order_id: str = ""
    task_fixture_id: str = ""
    task_family: str = ""
    estimated_value_usd: float = 0.0

    # Worker
    worker: WorkerVersion = field(default_factory=WorkerVersion)

    # World
    world_genome_id: str = ""
    world_seed: int = 0
    evaluator_version: str = "v1"

    # Compute
    compute: ComputePolicy = field(default_factory=ComputePolicy)
    provider_requests: list[ProviderRequest] = field(default_factory=list)

    # Git
    base_sha: str = ""   # B0
    final_sha: str = ""  # B1
    diff_sha: str = ""
    changed_files: list[str] = field(default_factory=list)

    # Evaluation
    evaluation: Evaluation = field(default_factory=Evaluation)

    # Economics
    actual_cost_usd: float = 0.0
    latency_ms: int = 0
    realized_reward_usd: float = 0.0

    # Evidence
    trajectory_ref: str = ""
    receipt_hash: str = ""
    artifact_hashes: list[str] = field(default_factory=list)

    # Metadata
    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def compute_receipt_hash(self) -> str:
        """Content-addressed receipt of this run."""
        d = {
            "run_id": self.run_id,
            "worker_id": self.worker.worker_id,
            "worker_version": self.worker.version,
            "world_genome_id": self.world_genome_id,
            "base_sha": self.base_sha,
            "final_sha": self.final_sha,
            "evaluation_success": self.evaluation.success,
            "evaluation_quality": self.evaluation.quality,
            "actual_cost_usd": self.actual_cost_usd,
        }
        self.receipt_hash = _sha256(d)[:16]
        return self.receipt_hash

    def to_hydra_record(self) -> dict:
        """Convert to dict for Hydra record_run."""
        return {
            "run_id": self.run_id,
            "world_genome_id": self.world_genome_id,
            "worker_genome_id": f"{self.worker.worker_id}/{self.worker.version}",
            "family_id": self.task_family,
            "harness": self.compute.policy_id,
            "model": self.provider_requests[0].model if self.provider_requests else "",
            "cost_usd": self.actual_cost_usd,
            "duration_ms": self.latency_ms,
            "model_calls": len(self.provider_requests),
            "success": self.evaluation.success,
            "quality_score": self.evaluation.quality,
            "failure_vector": {
                "modes": self.evaluation.failure_vector.modes,
                "severity": self.evaluation.failure_vector.severity,
                "gates_passed": sum(1 for g in self.evaluation.gates if g.passed),
                "gates_total": len(self.evaluation.gates),
                "capabilities": {c.capability: c.score for c in self.evaluation.capabilities},
            },
        }

    def save(self, path: str | Path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "campaign_id": self.campaign_id,
            "opportunity_id": self.opportunity_id,
            "task_family": self.task_family,
            "estimated_value_usd": self.estimated_value_usd,
            "worker": asdict(self.worker),
            "world_genome_id": self.world_genome_id,
            "world_seed": self.world_seed,
            "evaluator_version": self.evaluator_version,
            "compute": asdict(self.compute),
            "provider_requests": [asdict(r) for r in self.provider_requests],
            "base_sha": self.base_sha,
            "final_sha": self.final_sha,
            "diff_sha": self.diff_sha,
            "changed_files": self.changed_files,
            "evaluation": {
                "success": self.evaluation.success,
                "quality": self.evaluation.quality,
                "correctness": self.evaluation.correctness,
                "completeness": self.evaluation.completeness,
                "gates": [asdict(g) for g in self.evaluation.gates],
                "capabilities": [asdict(c) for c in self.evaluation.capabilities],
                "failure_vector": asdict(self.evaluation.failure_vector),
            },
            "actual_cost_usd": self.actual_cost_usd,
            "latency_ms": self.latency_ms,
            "receipt_hash": self.receipt_hash,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorkerRun:
        wr = cls()
        wr.run_id = d.get("run_id", wr.run_id)
        wr.campaign_id = d.get("campaign_id", "")
        wr.opportunity_id = d.get("opportunity_id", "")
        wr.task_family = d.get("task_family", "")
        wr.estimated_value_usd = d.get("estimated_value_usd", 0)
        wr.world_genome_id = d.get("world_genome_id", "")
        wr.world_seed = d.get("world_seed", 0)
        wr.evaluator_version = d.get("evaluator_version", "v1")
        wr.base_sha = d.get("base_sha", "")
        wr.final_sha = d.get("final_sha", "")
        wr.diff_sha = d.get("diff_sha", "")
        wr.changed_files = d.get("changed_files", [])
        wr.actual_cost_usd = d.get("actual_cost_usd", 0)
        wr.latency_ms = d.get("latency_ms", 0)
        wr.receipt_hash = d.get("receipt_hash", "")
        wr.created_at = d.get("created_at", time.time())

        w = d.get("worker", {})
        wr.worker = WorkerVersion(
            worker_id=w.get("worker_id", ""),
            version=w.get("version", "v1"),
            parent_version=w.get("parent_version", ""),
            letta_agent_id=w.get("letta_agent_id", ""),
            memfs_commit=w.get("memfs_commit", ""),
            skills_commit=w.get("skills_commit", ""),
            process_version=w.get("process_version", "default"),
        )

        c = d.get("compute", {})
        wr.compute = ComputePolicy(
            policy_id=c.get("policy_id", ""),
            arm=c.get("arm", "M"),
            budget_usd=c.get("budget_usd", 0.05),
            max_requests=c.get("max_requests", 3),
        )

        for r in d.get("provider_requests", []):
            wr.provider_requests.append(ProviderRequest(**r))

        e = d.get("evaluation", {})
        wr.evaluation = Evaluation(
            success=e.get("success", False),
            quality=e.get("quality", 0),
            correctness=e.get("correctness", 0),
            completeness=e.get("completeness", 0),
        )
        for g in e.get("gates", []):
            wr.evaluation.gates.append(GateResult(**g))
        for cap in e.get("capabilities", []):
            wr.evaluation.capabilities.append(CapabilityScore(**cap))
        fv = e.get("failure_vector", {})
        wr.evaluation.failure_vector = FailureVector(
            modes=fv.get("modes", []),
            severity=fv.get("severity", 0),
        )

        return wr
