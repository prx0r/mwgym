"""Wired Loop v2 — fixed Git, Letta, capabilities, stats.

Fixes from v1:
  1. Git: one lab repo + worktrees (not separate repos)
  2. Letta: persistent researcher-v1 agent, fresh session per run
  3. Capabilities: harness passes capabilities to FailureVector
  4. Worker genome + experiment recorded in Hydra
  5. World genome stats updated after runs
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path("/root/mwgym")))
sys.path.insert(0, str(Path("/root/workerkit")))

from mwgym.schema.world import WorldGenome, FailureVector, GateResult, CapabilityScore
from mwgym.worlds.cge_adapter import compile_world, ActionResult
from mwgym.worlds.adversary import Adversary
from mwgym.worlds.curriculum import Curriculum, CurriculumConfig
from mwgym.worlds.schema import get_family
from mwgym.hydra_unified import UnifiedHydra
from mwgym.harnesses.pydantic_bats import PydanticBATSHarness, UsageLimits
from mwgym.workspace import LabWorkspace
from mwgym.lab_brief import generate_brief


# ─── Letta harness (persistent agent, fresh session) ──────────────────

RUNTIME_URL = "http://localhost:3000"
WORKER_ID = "researcher-v1"  # persistent agent with 29 runs


def letta_request(method: str, path: str, data: dict = None,
                  timeout: int = 180) -> dict:
    url = f"{RUNTIME_URL}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"},
                                 method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def run_letta(task: str, workspace: str, brief_context: str = "",
              genome: dict | None = None, timeout: int = 300) -> tuple[dict, dict]:
    """Run via Letta. Persistent agent, fresh session, cwd = worktree.

    Default timeout 300s (5 min). Letta with mimo-v2.5 reasoning does 5+ passes
    at 4-15s each = easily 60-120s. HTTP timeout must exceed runtime timeout.
    """
    t0 = time.time()

    # Ensure worker exists
    letta_request("POST", "/workers", {
        "worker_id": WORKER_ID,
        "model": "opencode-go/mimo-v2.5",
        "persona": "You are a Moltwork worker. Complete tasks precisely. Return ActionBundle JSON.",
    })

    user_msg = task
    if brief_context:
        user_msg += f"\n\n{brief_context}"
    user_msg += "\n\nReturn a JSON ActionBundle: {\"status\": \"complete\", \"writes\": [{\"path\": \"file\", \"content\": \"data\"}], \"notes\": \"what you did\"}"

    result = letta_request("POST", f"/workers/{WORKER_ID}/run", {
        "task": user_msg,
        "workspace": workspace,
        "timeout": timeout,
        "genome": genome or {"memory_mode": "letta", "max_steps": 4},
        "allowedTools": ["Read", "Write", "Edit", "LS", "Glob", "Grep"],
    }, timeout=timeout + 60)  # HTTP timeout > runtime timeout

    duration_ms = int((time.time() - t0) * 1000)

    meta = {
        "harness": "letta-stateful",
        "model": "mimo-v2.5",
        "duration_ms": duration_ms,
        "agent_id": result.get("agent_id", ""),
        "conversation_id": result.get("conversation_id", ""),
        "tool_calls_count": len(result.get("tool_calls", [])),
    }
    return result, meta


# ─── Seed world ───────────────────────────────────────────────────────

def make_seed_world(family_id: str, difficulty: int = 2) -> WorldGenome:
    spec = get_family(family_id)
    caps = list(spec.capabilities) if spec else ["reasoning.default"]
    return WorldGenome(
        id=f"seed-{family_id}-001",
        family_id=family_id,
        difficulty=difficulty,
        seed=42,
        structure={"max_steps": 5, "capabilities": caps},
        information={"observable_fraction": 0.7, "conflicting_sources": 0.1,
                     "stale_sources": 0.1, "distractors": 0.2},
        resources={"budget_usd": 0.05, "free_calls": 5},
    )


def world_to_files(world: WorldGenome, state) -> dict[str, str]:
    return {
        "task.json": json.dumps({
            "world_id": world.id, "family_id": world.family_id,
            "difficulty": world.difficulty,
            "observable": state.observable,
            "available_actions": [a["kind"] for a in state.available_actions],
        }, indent=2),
        "README.md": f"# Task: {world.family_id}\n\nDifficulty: {world.difficulty}\n",
    }


# ─── Parse ActionBundle from any harness output ───────────────────────

def parse_bundle(text: str) -> dict:
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            b = json.loads(text[start:end])
            return {"status": b.get("status", "unknown"),
                    "writes": b.get("writes", []),
                    "notes": b.get("notes", "")}
    except json.JSONDecodeError:
        pass
    return {"status": "parse_error", "writes": [], "notes": text[:200]}


# ─── Main Loop ────────────────────────────────────────────────────────

def run_wired_loop(
    n_rounds: int = 10,
    family_id: str = "compute.routing",
    harness_kinds: list[str] | None = None,
    budget_per_round: float = 0.02,
):
    harness_kinds = harness_kinds or ["pydantic-bats"]

    hydra = UnifiedHydra()
    lab = LabWorkspace()
    adversary = Adversary(family_id=family_id)
    curriculum = Curriculum(adversary, CurriculumConfig(batch_size=3))

    # Record experiment
    experiment_id = f"exp-{family_id}-{int(time.time())}"
    hydra.record_experiment(
        experiment_id=experiment_id,
        hypothesis=f"Comparing {', '.join(harness_kinds)} on {family_id}",
        family_id=family_id,
        config={"rounds": n_rounds, "budget": budget_per_round},
    )

    # Record worker genomes
    for kind in harness_kinds:
        hydra.record_worker_genome(
            genome_id=f"worker-{kind}",
            harness=kind,
            model="mimo-v2.5",
        )

    # Seed world
    parent_world = make_seed_world(family_id)
    hydra.record_world_genome(parent_world)

    stats = {k: {"runs": 0, "success": 0, "total_cost": 0.0, "total_ms": 0,
                 "qualities": []} for k in harness_kinds}

    all_results = []

    for round_num in range(n_rounds):
        print(f"\n{'='*60}")
        print(f"ROUND {round_num + 1}/{n_rounds}")
        print(f"{'='*60}")

        # Pick world
        if round_num == 0 or not adversary.archive:
            current_world = parent_world
        else:
            selections = curriculum.select_next()
            if selections:
                wdata = hydra.get_world_genome(selections[0]["world_id"])
                if wdata:
                    current_world = WorldGenome.from_dict(wdata)
                else:
                    current_world = parent_world
            else:
                current_world = parent_world

        world = compile_world(current_world)
        state = world.reset(seed=round_num * 100 + 1)
        harness_kind = harness_kinds[round_num % len(harness_kinds)]

        # Step 1: Git worktree
        run_id = f"run-{family_id}-{round_num:03d}"
        wt = lab.create_run(run_id)
        world_files = world_to_files(current_world, state)
        wt.seed_world(world_files, f"world: {current_world.id}")

        print(f"World: {current_world.id} (diff={current_world.difficulty})")
        print(f"Worktree: {wt.path}")
        print(f"Branch: {wt.branch}")
        print(f"Harness: {harness_kind}")

        # Step 2: LabBrief
        brief = generate_brief(hydra, family_id)
        brief_text = brief.to_context() if brief.total_runs > 0 else ""
        print(f"Brief: {brief.total_runs} prior runs")

        # Step 5-6: Execute
        task = f"Complete the {family_id} task. See task.json for details."

        if harness_kind == "letta":
            result, meta = run_letta(task, wt.path, brief_text)
            output = result.get("output_content", "")
            ok = result.get("ok", bool(output))
            cost_usd = 0.0
            model_calls_list = [{"model": "mimo-v2.5", **meta}]
        else:
            harness = PydanticBATSHarness()
            run_obj, fv = harness.run(
                task=task,
                workspace=wt.path,
                limits=UsageLimits(request_limit=1, cost_limit_usd=budget_per_round,
                                   wall_time_limit_s=30),
                world_genome_id=current_world.id,
                worker_genome_id=f"worker-{harness_kind}",
                family_id=family_id,
                uncertainty=0.5 + (current_world.difficulty / 20),
            )
            output = run_obj.output
            ok = run_obj.ok
            cost_usd = run_obj.cost_usd
            meta = run_obj.metadata
            model_calls_list = run_obj.model_calls

        # Step 7: Git commit
        wt.commit_worker_output(f"worker ({harness_kind}): {ok}")

        # Build capability scores from world scoring
        capabilities = world._score_capabilities(state)
        gates = world._evaluate_gates(state)

        # Build FailureVector
        if harness_kind == "letta":
            modes = []
            if not ok:
                modes.append("execution_failed")
            fv = FailureVector(
                run_id=run_id,
                world_genome_id=current_world.id,
                worker_genome_id=f"worker-{harness_kind}",
                gates=tuple(gates),
                gates_passed=sum(1 for g in gates if g.passed),
                gates_total=len(gates),
                capabilities=tuple(capabilities),
                failure_modes=tuple(modes),
                quality_score=1.0 if ok else 0.0,
                duration_ms=meta.get("duration_ms", 0),
                model_calls=len(model_calls_list),
            )

        # Step 8: Hydra record
        hydra.record_run(
            run_id=run_id,
            world_genome_id=current_world.id,
            worker_genome_id=f"worker-{harness_kind}",
            family_id=family_id,
            harness=harness_kind,
            model=meta.get("model", "mimo-v2.5"),
            cost_usd=cost_usd,
            duration_ms=meta.get("duration_ms", 0),
            model_calls=len(model_calls_list),
            success=ok,
            quality_score=fv.quality_score,
            failure_vector=fv,
            experiment_id=experiment_id,
        )

        # Record capabilities (FIX: actually write them)
        for cap in capabilities:
            hydra.record_capability(
                worker_genome_id=f"worker-{harness_kind}",
                family_id=family_id,
                capability=cap.capability,
                score=cap.score,
            )

        # Record failure modes
        for mode in fv.failure_modes:
            hydra.record_failure_mode(family_id, mode, fv.failure_severity,
                                       worker_id=f"worker-{harness_kind}")

        # Record graph
        hydra.add_node(f"run:{run_id}", "Run", {
            "run_id": run_id, "harness": harness_kind, "success": ok,
            "branch": wt.branch, "base_commit": wt.base_commit,
            "final_commit": wt.final_commit,
        })
        hydra.add_node(f"world:{current_world.id}", "WorldGenome", {
            "id": current_world.id, "difficulty": current_world.difficulty,
        })
        hydra.add_edge(f"run:{run_id}", f"world:{current_world.id}", "EXECUTED_IN")

        # Step 9: Adversary
        child, strategy, niche = adversary.mutate(current_world, fv)
        score = adversary.objective(fv, child)
        adversary.archive_world(child, fv, score)
        hydra.record_world_genome(child)

        # Update world genome stats (FIX)
        world_runs = hydra.get_runs(world_genome_id=current_world.id)
        if world_runs:
            mean_q = sum(r["quality_score"] for r in world_runs) / len(world_runs)
            mean_c = sum(r["cost_usd"] for r in world_runs) / len(world_runs)
            mean_d = sum(r["duration_ms"] for r in world_runs) / len(world_runs)
            success_rate = sum(1 for r in world_runs if r["success"]) / len(world_runs)
            hydra.update_world_genome_stats(
                current_world.id, len(world_runs), mean_q, mean_c, mean_d, success_rate)

        # Track stats
        stats[harness_kind]["runs"] += 1
        if ok:
            stats[harness_kind]["success"] += 1
        stats[harness_kind]["total_cost"] += cost_usd
        stats[harness_kind]["total_ms"] += meta.get("duration_ms", 0)
        stats[harness_kind]["qualities"].append(fv.quality_score)

        entry = {
            "round": round_num, "harness": harness_kind,
            "world": current_world.id, "difficulty": current_world.difficulty,
            "success": ok, "model": meta.get("model", ""),
            "cost_usd": cost_usd, "duration_ms": meta.get("duration_ms", 0),
            "quality": fv.quality_score, "severity": fv.failure_severity,
            "failure_modes": list(fv.failure_modes),
            "capabilities": [(c.capability, round(c.score, 2)) for c in capabilities],
            "strategy": strategy, "branch": wt.branch,
            "base_commit": wt.base_commit, "final_commit": wt.final_commit,
        }
        all_results.append(entry)

        print(f"\nResult: {'OK' if ok else 'FAIL'}")
        print(f"Model: {meta.get('model', '?')}")
        print(f"Duration: {meta.get('duration_ms', 0)}ms")
        print(f"Quality: {fv.quality_score:.2f}")
        print(f"Capabilities: {[(c.capability, round(c.score, 2)) for c in capabilities]}")
        print(f"Git: {wt.branch} | {wt.base_commit[:8]} → {wt.final_commit[:8] if wt.final_commit else 'none'}")
        print(f"Adversary: strategy={strategy}, child diff={child.difficulty}")

    # Report
    print(f"\n{'='*60}")
    print("EXPERIMENT REPORT")
    print(f"{'='*60}")
    print(f"Experiment: {experiment_id}")
    print(f"Family: {family_id}")

    for kind in harness_kinds:
        s = stats[kind]
        wr = s["success"] / s["runs"] * 100 if s["runs"] else 0
        avg_q = sum(s["qualities"]) / len(s["qualities"]) if s["qualities"] else 0
        avg_ms = s["total_ms"] / s["runs"] if s["runs"] else 0
        print(f"\n{kind}:")
        print(f"  Runs: {s['runs']}")
        print(f"  Success: {wr:.0f}%")
        print(f"  Avg quality: {avg_q:.2f}")
        print(f"  Avg duration: {avg_ms:.0f}ms")

    print(f"\nAdversary: {len(adversary.archive)} worlds, {adversary.mutation_counts}")

    summary = hydra.summary()
    print(f"Hydra: runs={summary['total_runs']}, worlds={summary['total_worlds']}, workers={summary['total_workers']}")
    fs = hydra.family_stats(family_id)
    print(f"Family: runs={fs['total_runs']}, quality={fs['mean_quality']:.2f}, worlds={fs['total_worlds']}")
    print(f"Top failures: {fs['top_failures']}")

    # Check capabilities actually recorded
    caps = hydra.get_capabilities(f"worker-pydantic-bats", family_id)
    print(f"Capability evidence rows: {len(caps)}")
    for c in caps[:5]:
        print(f"  {c['capability']}: score={c['mean_score']:.2f} n={c['n_samples']}")

    # Save
    results_path = f"/root/mwgym/data/experiment-{experiment_id}.json"
    Path(results_path).parent.mkdir(parents=True, exist_ok=True)
    Path(results_path).write_text(json.dumps({
        "experiment_id": experiment_id, "family_id": family_id,
        "harness_kinds": harness_kinds, "n_rounds": n_rounds,
        "results": all_results, "stats": stats,
    }, indent=2))
    print(f"\nSaved: {results_path}")

    return all_results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--family", default="compute.routing")
    parser.add_argument("--harness", default="pydantic-bats")
    parser.add_argument("--budget", type=float, default=0.02)
    args = parser.parse_args()
    kinds = args.harness.split(",") if "," in args.harness else [args.harness]
    run_wired_loop(n_rounds=args.rounds, family_id=args.family,
                   harness_kinds=kinds, budget_per_round=args.budget)
