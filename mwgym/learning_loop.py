"""Learning Loop — BATS reads Hydra, proposes learning, promotes skills.

The missing piece: BATS still uses hardcoded quality scores.
This module makes BATS read from Hydra empirical data,
proposes learning from failure patterns, and promotes validated skills.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ─── 1. Hydra-Aware BATS ──────────────────────────────────────────────

@dataclass
class HydraPosterior:
    """Real empirical stats from Hydra for routing decisions."""
    model: str = ""
    family: str = ""
    n_runs: int = 0
    success_rate: float = 0.0
    mean_quality: float = 0.0
    mean_cost_usd: float = 0.0
    mean_duration_ms: float = 0.0
    mean_tokens: float = 0.0


def query_hydra_posterior(hydra, model: str, family: str) -> HydraPosterior:
    """Query Hydra for real stats on model × family."""
    import sqlite3
    conn = sqlite3.connect(hydra.db_path)
    conn.row_factory = sqlite3.Row

    row = conn.execute("""
        SELECT COUNT(*) as n,
               AVG(CASE WHEN success=1 THEN 1.0 ELSE 0.0 END) as success_rate,
               AVG(quality_score) as mean_quality,
               AVG(cost_usd) as mean_cost,
               AVG(duration_ms) as mean_duration,
               AVG(prompt_tokens + completion_tokens) as mean_tokens
        FROM runs
        WHERE model=? AND family_id=?
    """, (model, family)).fetchone()

    conn.close()

    if row and row["n"] > 0:
        return HydraPosterior(
            model=model, family=family,
            n_runs=row["n"],
            success_rate=row["success_rate"] or 0.0,
            mean_quality=row["mean_quality"] or 0.0,
            mean_cost_usd=row["mean_cost"] or 0.0,
            mean_duration_ms=row["mean_duration"] or 0.0,
            mean_tokens=row["mean_tokens"] or 0.0,
        )
    return HydraPosterior(model=model, family=family)


def smart_route(hydra, task_type: str, budget_remaining: float,
                models: list[str] | None = None) -> dict:
    """Route using Hydra posterior instead of hardcoded scores.

    Returns: {model, reason, estimated_cost, posterior_n, posterior_quality}
    """
    from mwgym.harnesses.pydantic_bats import BATSRouter
    router = BATSRouter()
    models = models or list(router.MODELS.keys())

    # Get posterior for each model
    posteriors = {}
    for model in models:
        post = query_hydra_posterior(hydra, model, task_type)
        posteriors[model] = post

    # Find cheapest model that meets quality threshold
    # Use posterior if available, fallback to router defaults
    candidates = []
    for model in models:
        post = posteriors[model]
        router_model = router.MODELS.get(model, {})
        quality = post.mean_quality if post.n_runs >= 3 else router_model.get("quality", 0.5)
        cost_per_call = router.estimate_cost(model, 1000, 500)

        if budget_remaining >= cost_per_call:
            candidates.append({
                "model": model,
                "quality": quality,
                "cost": cost_per_call,
                "n": post.n_runs,
                "success_rate": post.success_rate,
            })

    if not candidates:
        # Fallback to cheapest
        return {"model": models[0], "reason": "no_candidates",
                "estimated_cost": 0.0, "posterior_n": 0, "posterior_quality": 0.0}

    # Sort by quality, pick best affordable
    candidates.sort(key=lambda c: c["quality"], reverse=True)
    best = candidates[0]

    # Check if we have real data
    reason = "hydra_posterior" if best["n"] >= 3 else "router_default"

    return {
        "model": best["model"],
        "reason": reason,
        "estimated_cost": best["cost"],
        "posterior_n": best["n"],
        "posterior_quality": best["quality"],
        "success_rate": best["success_rate"],
    }


# ─── 2. Capability Evidence Recorder ──────────────────────────────────

def record_run_capabilities(hydra, run_id: str, family_id: str,
                             model: str, output: str,
                             expected_capabilities: list[str] | None = None):
    """Record capability evidence from a run.

    Evaluates output against expected capabilities and records scores.
    """
    if not expected_capabilities:
        return

    for cap in expected_capabilities:
        # Simple heuristic scoring based on output characteristics
        score = 0.5  # baseline
        output_lower = output.lower()

        if cap == "code.understand":
            score = 0.8 if any(kw in output_lower for kw in ["class ", "def ", "import "]) else 0.3
        elif cap == "code.write":
            score = 0.9 if any(kw in output_lower for kw in ["class ", "def ", "return "]) else 0.2
        elif cap == "code.debug":
            score = 0.7 if "fix" in output_lower or "error" in output_lower else 0.5
        elif cap == "source.verify":
            score = 0.8 if any(kw in output_lower for kw in ["evidence", "source", "cited"]) else 0.4
        elif cap == "reasoning.default":
            score = 0.7 if len(output) > 200 else 0.4
        elif cap == "model.select":
            score = 0.6  # can't evaluate from output alone
        elif cap == "budget.allocate":
            score = 0.6
        else:
            score = 0.5

        hydra.record_capability(
            worker_genome_id=f"worker-{model}",
            family_id=family_id,
            capability=cap,
            score=score,
        )


# ─── 3. Learning Proposal ─────────────────────────────────────────────

@dataclass
class LearningProposal:
    """A proposed change to worker memory/skill based on failure analysis."""
    proposal_id: str = ""
    target: str = ""           # "memory", "skill", "process"
    path: str = ""             # e.g. "skills/routing/SKILL.md"
    hypothesis: str = ""
    patch: str = ""
    source_runs: list[str] = field(default_factory=list)
    expected_effects: list[str] = field(default_factory=list)
    confidence: float = 0.0


def reflect_on_failures(hydra, family_id: str) -> list[LearningProposal]:
    """Analyze failure patterns and propose learning.

    This is the reflection step: look at what failed, why, and propose fixes.
    """
    proposals = []

    # Get failure modes
    failures = hydra.get_failure_modes(family_id, min_frequency=0.2)

    # Get recent runs
    runs = hydra.get_runs(family_id=family_id, limit=20)
    failed_runs = [r for r in runs if not r["success"]]
    successful_runs = [r for r in runs if r["success"]]

    if not failed_runs:
        return proposals

    # Analyze failure patterns
    failure_modes = {}
    for run in failed_runs:
        fv = run.get("failure_vector", {})
        for mode in fv.get("failure_modes", []):
            failure_modes[mode] = failure_modes.get(mode, 0) + 1

    # Propose fixes for most common failures
    for mode, count in sorted(failure_modes.items(), key=lambda x: -x[1]):
        if count < 2:
            continue

        if mode == "execution_failed":
            proposals.append(LearningProposal(
                proposal_id=f"prop-{family_id}-exec-{int(time.time())}",
                target="skill",
                path=f"skills/{family_id}/execution-checklist.md",
                hypothesis=f"Adding execution checklist reduces execution_failed (seen {count}x)",
                patch=f"# Execution Checklist for {family_id}\n\n"
                      "1. Read task requirements completely\n"
                      "2. Plan implementation before coding\n"
                      "3. Write code incrementally\n"
                      "4. Test before declaring complete\n",
                source_runs=[r["run_id"] for r in failed_runs[:5]],
                expected_effects=["execution_rate_up", "quality_up"],
                confidence=min(0.7, count / 10),
            ))
        elif mode == "no_artifacts":
            proposals.append(LearningProposal(
                proposal_id=f"prop-{family_id}-artifacts-{int(time.time())}",
                target="memory",
                path=f"memories/{family_id}/artifact-reminder.md",
                hypothesis=f"Explicit artifact reminder reduces no_artifacts (seen {count}x)",
                patch=f"# Artifact Reminder\n\n"
                      f"For {family_id} tasks, always produce at least one .py file.\n"
                      "Return ActionBundle with writes array populated.\n",
                source_runs=[r["run_id"] for r in failed_runs[:5]],
                expected_effects=["artifact_rate_up"],
                confidence=min(0.6, count / 10),
            ))
        elif mode == "model_error":
            proposals.append(LearningProposal(
                proposal_id=f"prop-{family_id}-model-{int(time.time())}",
                target="process",
                path=f"processes/{family_id}/model-fallback.md",
                hypothesis=f"Adding model fallback reduces model_error (seen {count}x)",
                patch=f"# Model Fallback\n\n"
                      "If primary model fails, retry with fallback model.\n"
                      "Primary: mimo-v2.5\n"
                      "Fallback: llama-3.1-8b-instant\n",
                source_runs=[r["run_id"] for r in failed_runs[:5]],
                expected_effects=["error_rate_down"],
                confidence=min(0.5, count / 10),
            ))

    return proposals


# ─── 4. Promotion Gate ────────────────────────────────────────────────

@dataclass
class PromotionResult:
    """Result of a promotion gate test."""
    promoted: bool = False
    candidate_id: str = ""
    incumbent_id: str = ""
    candidate_quality: float = 0.0
    incumbent_quality: float = 0.0
    improvement: float = 0.0
    gate_passed: bool = False
    reason: str = ""


def promotion_gate(hydra, candidate_proposal: LearningProposal,
                    held_out_tasks: list[str] | None = None) -> PromotionResult:
    """Test a learning proposal against held-out tasks.

    Returns PromotionResult with whether to promote.
    """
    # For now, simple heuristic: if proposal confidence > 0.5 and we have evidence
    # In production: run candidate on held_out_tasks, compare to incumbent

    if not held_out_tasks:
        # No held-out tasks available — use confidence as proxy
        promoted = candidate_proposal.confidence > 0.6
        return PromotionResult(
            promoted=promoted,
            candidate_id=candidate_proposal.proposal_id,
            candidate_quality=candidate_proposal.confidence,
            improvement=candidate_proposal.confidence - 0.5,
            gate_passed=promoted,
            reason=f"confidence={candidate_proposal.confidence:.2f} > 0.6" if promoted
                   else f"confidence={candidate_proposal.confidence:.2f} <= 0.6",
        )

    # Run candidate on held-out tasks
    # Compare to incumbent baseline
    # This is the real promotion gate
    return PromotionResult(
        promoted=False,
        candidate_id=candidate_proposal.proposal_id,
        reason="held_out evaluation not yet implemented",
    )


# ─── 5. Trajectory Recorder ───────────────────────────────────────────

@dataclass
class TrajectoryEvent:
    """One step in a run's trajectory."""
    event_type: str = ""     # "model_call", "tool_call", "file_write", "decision"
    timestamp_ms: int = 0
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    content_preview: str = ""
    metadata: dict = field(default_factory=dict)


def record_trajectory(hydra, run_id: str, events: list[TrajectoryEvent]):
    """Record trajectory events to Hydra."""
    import sqlite3
    conn = sqlite3.connect(hydra.db_path)
    # Store as JSON in a trajectory table (create if needed)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trajectories (
            run_id TEXT,
            events TEXT,
            created_at REAL
        )
    """)
    conn.execute("""
        INSERT INTO trajectories (run_id, events, created_at)
        VALUES (?, ?, ?)
    """, (run_id, json.dumps([e.__dict__ for e in events]), time.time()))
    conn.commit()
    conn.close()


def get_trajectory(hydra, run_id: str) -> list[dict]:
    """Get trajectory for a run."""
    import sqlite3
    conn = sqlite3.connect(hydra.db_path)
    try:
        row = conn.execute(
            "SELECT events FROM trajectories WHERE run_id=?", (run_id,)
        ).fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except:
        conn.close()
    return []


# ─── 6. Full Learning Loop ────────────────────────────────────────────

def run_learning_step(hydra, family_id: str, model: str = "mimo-v2.5") -> dict:
    """One step of the learning loop.

    1. Query Hydra posterior for routing
    2. Analyze failures
    3. Propose learning
    4. Test promotion gate
    """
    # 1. Get routing posterior
    posterior = query_hydra_posterior(hydra, model, family_id)

    # 2. Analyze failures
    failures = hydra.get_failure_modes(family_id, min_frequency=0.1)

    # 3. Propose learning
    proposals = reflect_on_failures(hydra, family_id)

    # 4. Test promotion
    promotion_results = []
    for prop in proposals:
        result = promotion_gate(hydra, prop)
        promotion_results.append(result)

    return {
        "family": family_id,
        "model": model,
        "posterior": {
            "n_runs": posterior.n_runs,
            "success_rate": posterior.success_rate,
            "mean_quality": posterior.mean_quality,
        },
        "failure_modes": [{"mode": f["failure_mode"], "freq": f["frequency"]}
                         for f in failures[:5]],
        "proposals": len(proposals),
        "promoted": sum(1 for r in promotion_results if r.promoted),
        "proposal_details": [
            {"id": p.proposal_id, "target": p.target, "hypothesis": p.hypothesis[:80],
             "confidence": p.confidence, "promoted": r.promoted}
            for p, r in zip(proposals, promotion_results)
        ],
    }
