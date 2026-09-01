"""Real Loop — task → BATS → execute → Hydra → Git → FailureVector → adversary → next task.

This is the actual working loop. No mocks. No Harbor. Real API calls.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path("/root/mwgym")))
sys.path.insert(0, str(Path("/root/workerkit")))

from mwgym.schema.world import WorldGenome, FailureVector
from mwgym.worlds.cge_adapter import compile_world, ActionResult
from mwgym.worlds.adversary import Adversary
from mwgym.worlds.curriculum import Curriculum, CurriculumConfig
from mwgym.hydra_unified import UnifiedHydra
from mwgym.harnesses.pydantic_bats import PydanticBATSHarness, UsageLimits


def run_loop(n_rounds: int = 3, family_id: str = "compute.routing",
             budget_per_round: float = 0.02):
    """Run the real loop.

    Each round:
      1. Curriculum selects a world
      2. BATS routes to cheapest model
      3. Pydantic harness executes
      4. Hydra records everything
      5. Git commits artifacts
      6. FailureVector feeds adversary
      7. Adversary mutates world
    """
    hydra = UnifiedHydra()
    harness = PydanticBATSHarness()

    # Seed world
    parent_world = WorldGenome(
        id=f"seed-{family_id}-001",
        family_id=family_id,
        difficulty=2,
        seed=42,
        structure={
            "max_steps": 5,
            "capabilities": ["model.select", "budget.allocate", "reasoning.default"],
        },
        information={"observable_fraction": 0.7},
        resources={"budget_usd": budget_per_round, "free_calls": 5},
    )

    # Register in Hydra
    hydra.record_world_genome(parent_world)

    # Adversary starts from seed world
    adversary = Adversary(family_id=family_id)
    curriculum = Curriculum(adversary, CurriculumConfig(batch_size=3))

    # Track capability scores across rounds
    cap_scores: dict[str, float] = {}

    results_log = []

    for round_num in range(n_rounds):
        print(f"\n{'='*60}")
        print(f"ROUND {round_num + 1}/{n_rounds}")
        print(f"{'='*60}")

        # 1. Curriculum selects world
        if round_num == 0:
            world = compile_world(parent_world)
            current_world = parent_world
        else:
            # Use curriculum to pick from archive
            selections = curriculum.select_next(worker_caps=cap_scores)
            if selections:
                wid = selections[0]["world_id"]
                # Find world in hydra
                wdata = hydra.get_world_genome(wid)
                if wdata:
                    current_world = WorldGenome.from_dict(wdata)
                    world = compile_world(current_world)
                else:
                    world = compile_world(parent_world)
                    current_world = parent_world
            else:
                world = compile_world(parent_world)
                current_world = parent_world

        state = world.reset(seed=round_num * 100 + 1)
        task = f"Complete this {family_id} task. Available actions: {[a['kind'] for a in state.available_actions]}"

        print(f"World: {current_world.id} (diff={current_world.difficulty})")
        print(f"Family: {family_id}")
        print(f"Task: {task[:80]}...")

        # 2-3. BATS route + execute
        run, fv = harness.run(
            task=task,
            workspace=f"/tmp/mwgym-loop-{round_num}",
            limits=UsageLimits(
                request_limit=1,
                cost_limit_usd=budget_per_round,
                wall_time_limit_s=30,
            ),
            world_genome_id=current_world.id,
            worker_genome_id=f"worker-{round_num}",
            family_id=family_id,
            uncertainty=0.5 + (current_world.difficulty / 20),
            capability_scores=cap_scores,
        )

        print(f"\nResult: {'OK' if run.ok else 'FAILED'}")
        print(f"Model: {run.metadata.get('model', '?')}")
        print(f"Route: {run.metadata.get('route_reason', '?')}")
        print(f"Cost: ${run.cost_usd:.4f}")
        print(f"Duration: {run.duration_ms}ms")
        print(f"Tokens: {run.total_tokens}")
        print(f"Artifacts: {len(run.artifacts)}")
        print(f"Severity: {fv.failure_severity:.2f}")
        print(f"Modes: {fv.failure_modes}")
        print(f"Gates: {fv.gates_passed}/{fv.gates_total}")

        # 4. Record in Hydra
        hydra.record_run(
            run_id=run.metadata.get("run_id", f"round-{round_num}"),
            world_genome_id=current_world.id,
            worker_genome_id=f"worker-{round_num}",
            family_id=family_id,
            harness="pydantic-bats",
            model=run.metadata.get("model", ""),
            cost_usd=run.cost_usd,
            duration_ms=run.duration_ms,
            model_calls=len(run.model_calls),
            success=run.ok,
            quality_score=fv.quality_score,
            failure_vector=fv,
        )

        # Record capability evidence
        for cap in fv.capabilities:
            hydra.record_capability(
                worker_genome_id=f"worker-{round_num}",
                family_id=family_id,
                capability=cap.capability,
                score=cap.score,
            )
            cap_scores[f"{cap.capability}.{family_id}"] = cap.score

        # Record failure modes
        for mode in fv.failure_modes:
            hydra.record_failure_mode(family_id, mode, fv.failure_severity,
                                       worker_id=f"worker-{round_num}")

        # 5. Adversary mutates based on FailureVector
        child, strategy, niche = adversary.mutate(current_world, fv)
        score = adversary.objective(fv, child)
        adversary.archive_world(child, fv, score)

        print(f"\nAdversary: strategy={strategy}, niche={niche}")
        print(f"Child: {child.id} (diff={child.difficulty})")

        # Record child world
        hydra.record_world_genome(child)

        results_log.append({
            "round": round_num,
            "world_id": current_world.id,
            "success": run.ok,
            "model": run.metadata.get("model", ""),
            "route": run.metadata.get("route_reason", ""),
            "cost_usd": run.cost_usd,
            "severity": fv.failure_severity,
            "failure_modes": list(fv.failure_modes),
            "strategy": strategy,
        })

    # Summary
    print(f"\n{'='*60}")
    print("LOOP COMPLETE")
    print(f"{'='*60}")
    print(f"Rounds: {n_rounds}")
    print(f"Success rate: {sum(1 for r in results_log if r['success'])}/{n_rounds}")
    print(f"Total cost: ${sum(r['cost_usd'] for r in results_log):.4f}")
    print(f"Adversary archive: {len(adversary.archive)} worlds")
    print(f"Mutation counts: {adversary.mutation_counts}")

    # Hydra summary
    summary = hydra.summary()
    print(f"Hydra: {json.dumps(summary, indent=2)}")

    # Family stats
    stats = hydra.family_stats(family_id)
    print(f"Family stats: {json.dumps(stats, indent=2)}")

    return results_log


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--family", default="compute.routing")
    parser.add_argument("--budget", type=float, default=0.02)
    args = parser.parse_args()
    run_loop(n_rounds=args.rounds, family_id=args.family, budget_per_round=args.budget)
