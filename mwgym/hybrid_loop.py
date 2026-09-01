"""Hybrid Loop — four-speed execution with Letta brain + Pydantic workers.

Architecture:
  Letta (persistent brain) plans and synthesizes
  Pydantic (cheap worker) executes bounded tasks
  Git tracks everything
  Hydra records empirical results
  Adversary mutates worlds

Four profiles:
  DIRECT       — raw model call, 1 turn, no memory
  BOUNDED      — Pydantic with UsageLimits, 1-3 calls
  STATEFUL_FAST — Letta agent, MemFS ON, tools OFF, dreaming OFF
  AGENTIC      — Letta agent, tools ON, full harness
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path("/root/mwgym")))
sys.path.insert(0, str(Path("/root/workerkit")))

from mwgym.schema.world import WorldGenome, FailureVector, GateResult, CapabilityScore
from mwgym.worlds.cge_adapter import compile_world, ActionResult
from mwgym.worlds.adversary import Adversary
from mwgym.worlds.curriculum import Curriculum, CurriculumConfig
from mwgym.worlds.schema import get_family
from mwgym.harnesses.pydantic_bats import PydanticBATSHarness, UsageLimits, _call_model, BATSRouter
from mwgym.workspace import LabWorkspace
from mwgym.lab_brief import generate_brief


# ─── Profile definitions ──────────────────────────────────────────────

@dataclass
class ExecutionProfile:
    """Four-speed execution profile."""
    name: str = "DIRECT"
    description: str = ""
    memory: bool = False
    max_calls: int = 1
    tools: list[str] = field(default_factory=list)
    dreaming: bool = False
    reasoning_effort: str = "low"


PROFILES = {
    "DIRECT": ExecutionProfile(
        name="DIRECT",
        description="Raw model call, 1 turn, no memory",
        memory=False, max_calls=1, tools=[],
        dreaming=False, reasoning_effort="low",
    ),
    "BOUNDED": ExecutionProfile(
        name="BOUNDED",
        description="Pydantic with UsageLimits, 1-3 calls",
        memory=False, max_calls=3, tools=[],
        dreaming=False, reasoning_effort="low",
    ),
    "STATEFUL_FAST": ExecutionProfile(
        name="STATEFUL_FAST",
        description="Letta agent, MemFS ON, tools OFF, dreaming OFF",
        memory=True, max_calls=1, tools=[],
        dreaming=False, reasoning_effort="low",
    ),
    "AGENTIC": ExecutionProfile(
        name="AGENTIC",
        description="Letta agent, tools ON, full harness",
        memory=True, max_calls=10,
        tools=["Read", "Write", "Edit", "LS", "Glob", "Grep"],
        dreaming=False, reasoning_effort="medium",
    ),
}


# ─── Letta runners ────────────────────────────────────────────────────

RUNTIME_URL = "http://localhost:3000"
WORKER_ID = "researcher-v1"


def _letta_post(path: str, data: dict, timeout: int = 300) -> dict:
    """POST to runtime-letta with long timeout."""
    url = f"{RUNTIME_URL}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def run_letta_direct(task: str, workspace: str) -> tuple[dict, dict]:
    """DIRECT profile: raw model call via OpenCode API. No Letta, no memory."""
    t0 = time.time()

    # Load API key
    api_url = "https://opencode.ai/zen/go/v1/chat/completions"
    api_key = ""
    for env_path in [Path("/root/workerkit/.env")]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("OPENCODE_API_KEY="):
                    api_key = line.split("=", 1)[1]

    system = "Complete the task. Return JSON ActionBundle: {\"status\": \"complete\", \"writes\": [{\"path\": \"file\", \"content\": \"data\"}], \"notes\": \"what you did\"}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]

    result = _call_model(api_url, api_key, "mimo-v2.5", messages,
                          max_tokens=4096, thinking="disabled", timeout=30)

    duration_ms = int((time.time() - t0) * 1000)
    output = result.get("content", "")

    # Parse and apply writes
    writes = []
    try:
        start = output.find("{")
        end = output.rfind("}") + 1
        if start >= 0:
            bundle = json.loads(output[start:end])
            writes = bundle.get("writes", [])
    except: pass

    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)
    applied = []
    for w in writes:
        if isinstance(w, dict) and "path" in w and "content" in w:
            p = ws / w["path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(w["content"])
            applied.append(w["path"])

    meta = {
        "profile": "DIRECT",
        "model": "mimo-v2.5",
        "duration_ms": duration_ms,
        "provider_requests": 1,
        "memory": False,
        "tools_used": [],
    }
    result = {"ok": len(applied) > 0 or bool(output), "output": output,
              "writes": applied}
    return result, meta


def run_letta_stateful_fast(task: str, workspace: str, genome: dict = None) -> tuple[dict, dict]:
    """STATEFUL_FAST: Letta agent, MemFS ON, tools OFF, dreaming OFF.

    mimo-v2.5 always does 5+ reasoning passes (~4s each) = ~60s minimum.
    Timeout set to 180s. Accept output if timed_out but output exists.
    """
    t0 = time.time()

    # Ensure worker
    _letta_post("/workers", {
        "worker_id": WORKER_ID,
        "model": "opencode-go/mimo-v2.5",
        "persona": "You are a Moltwork worker. Complete tasks precisely. Return ActionBundle JSON.",
    }, timeout=30)

    user_msg = f"{task}\n\nReturn a JSON ActionBundle: {{\"status\": \"complete\", \"writes\": [{{\"path\": \"file\", \"content\": \"data\"}}], \"notes\": \"what you did\"}}"

    result = _letta_post(f"/workers/{WORKER_ID}/run", {
        "task": user_msg,
        "workspace": workspace,
        "timeout": 180,
        "genome": genome or {"memory_mode": "letta", "max_steps": 1},
        "allowedTools": [],
    }, timeout=240)

    duration_ms = int((time.time() - t0) * 1000)
    output = result.get("output_content", "")
    timed_out = result.get("timed_out", False)
    ok = result.get("ok", False) or (timed_out and bool(output))

    meta = {
        "profile": "STATEFUL_FAST",
        "model": "mimo-v2.5",
        "duration_ms": duration_ms,
        "provider_requests": result.get("tool_calls", []),
        "memory": True,
        "tools_used": [],
        "agent_id": result.get("agent_id", ""),
        "conversation_id": result.get("conversation_id", ""),
    }
    return {"ok": ok, "output": output}, meta


def run_letta_agent(task: str, workspace: str, genome: dict = None) -> tuple[dict, dict]:
    """AGENTIC: Letta agent, tools ON, full harness."""
    t0 = time.time()

    _letta_post("/workers", {
        "worker_id": WORKER_ID,
        "model": "opencode-go/mimo-v2.5",
        "persona": "You are a Moltwork worker. Complete tasks precisely.",
    }, timeout=30)

    user_msg = f"{task}\n\nReturn a JSON ActionBundle: {{\"status\": \"complete\", \"writes\": [{{\"path\": \"file\", \"content\": \"data\"}}], \"notes\": \"what you did\"}}"

    result = _letta_post(f"/workers/{WORKER_ID}/run", {
        "task": user_msg,
        "workspace": workspace,
        "timeout": 180,
        "genome": genome or {"memory_mode": "letta", "max_steps": 4},
        "allowedTools": ["Read", "Write", "Edit", "LS", "Glob", "Grep"],
    }, timeout=240)

    duration_ms = int((time.time() - t0) * 1000)
    output = result.get("output_content", "")
    tool_calls = result.get("tool_calls", [])

    meta = {
        "profile": "AGENTIC",
        "model": "mimo-v2.5",
        "duration_ms": duration_ms,
        "provider_requests": len(tool_calls) + 1,
        "memory": True,
        "tools_used": [t.get("name", "") for t in tool_calls],
        "agent_id": result.get("agent_id", ""),
        "conversation_id": result.get("conversation_id", ""),
    }
    return {"ok": result.get("ok", bool(output)), "output": output,
            "tool_calls": tool_calls}, meta


def run_bounded(task: str, workspace: str, budget: float = 0.01) -> tuple[dict, dict]:
    """BOUNDED: Pydantic with UsageLimits, 1-3 calls."""
    from mwgym.harnesses.pydantic_bats import PydanticBATSHarness
    harness = PydanticBATSHarness()
    run_obj, fv = harness.run(
        task=task, workspace=workspace,
        limits=UsageLimits(request_limit=3, cost_limit_usd=budget,
                           wall_time_limit_s=60),
    )
    meta = {
        "profile": "BOUNDED",
        "model": run_obj.metadata.get("model", "mimo-v2.5"),
        "duration_ms": run_obj.duration_ms,
        "provider_requests": len(run_obj.model_calls),
        "memory": False,
        "tools_used": [],
        "cost_usd": run_obj.cost_usd,
    }
    result = {"ok": run_obj.ok, "output": run_obj.output,
              "writes": run_obj.metadata.get("writes", []),
              "failure_vector": fv}
    return result, meta


# ─── Dispatcher ───────────────────────────────────────────────────────

def dispatch(profile: str, task: str, workspace: str, **kwargs) -> tuple[dict, dict]:
    """Dispatch task to the right execution profile. Returns (result_dict, meta_dict)."""
    if profile == "DIRECT":
        return run_letta_direct(task, workspace)
    elif profile == "BOUNDED":
        return run_bounded(task, workspace, **kwargs)
    elif profile == "STATEFUL_FAST":
        return run_letta_stateful_fast(task, workspace, **kwargs)
    elif profile == "AGENTIC":
        return run_letta_agent(task, workspace, **kwargs)
    else:
        raise ValueError(f"Unknown profile: {profile}")


# ─── Hybrid loop ──────────────────────────────────────────────────────

def run_hybrid_loop(
    n_rounds: int = 10,
    family_id: str = "compute.routing",
    profiles: list[str] | None = None,
    budget_per_round: float = 0.02,
):
    """Hybrid loop: Letta brain + Pydantic workers.

    Each round:
      1. Git worktree
      2. LabBrief
      3. World compile
      4. Profile dispatch (DIRECT/BOUNDED/STATEFUL_FAST/AGENTIC)
      5. Git commit
      6. Hydra record
      7. FailureVector → adversary
      8. Report
    """
    profiles = profiles or ["DIRECT", "BOUNDED", "STATEFUL_FAST", "AGENTIC"]
    hydra = None  # TODO: Wire real HydraDB client
    lab = LabWorkspace()
    adversary = Adversary(family_id=family_id)
    curriculum = Curriculum(adversary, CurriculumConfig(batch_size=3))

    experiment_id = f"hybrid-{family_id}-{int(time.time())}"
    hydra.record_experiment(experiment_id,
        f"Four-speed hybrid: {', '.join(profiles)}", family_id=family_id)

    parent_world = WorldGenome(
        id=f"seed-{family_id}-001", family_id=family_id,
        difficulty=2, seed=42,
        structure={"max_steps": 5, "capabilities": ["model.select", "budget.allocate"]},
        information={"observable_fraction": 0.7},
        resources={"budget_usd": 0.05, "free_calls": 5},
    )
    hydra.record_world_genome(parent_world)

    stats = {p: {"runs": 0, "success": 0, "total_ms": 0, "qualities": []}
             for p in profiles}

    for round_num in range(n_rounds):
        profile = profiles[round_num % len(profiles)]
        print(f"\n{'='*60}")
        print(f"ROUND {round_num + 1}/{n_rounds} — {profile}")
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

        # Git worktree
        run_id = f"{profile.lower()}-{round_num:03d}"
        wt = lab.create_run(run_id)
        from mwgym.wired_loop import world_to_files
        wt.seed_world(world_to_files(current_world, state), f"world: {current_world.id}")

        # LabBrief
        brief = generate_brief(hydra, family_id)

        # Task
        task = f"Complete the {family_id} task. See task.json for details."

        # Dispatch
        print(f"  Profile: {PROFILES[profile].description}")
        print(f"  World: {current_world.id} (diff={current_world.difficulty})")

        result, meta = dispatch(profile, task, wt.path)

        # Git commit
        wt.commit_worker_output(f"{profile}: {result.get('ok', False)}")

        # FailureVector
        ok = result.get("ok", False)
        modes = []
        if not ok:
            modes.append("execution_failed")
        fv = FailureVector(
            run_id=run_id, world_genome_id=current_world.id,
            worker_genome_id=f"worker-{profile}",
            gates=(GateResult(gate_id="g0", gate_name="exec", passed=ok),),
            gates_passed=1 if ok else 0, gates_total=1,
            quality_score=1.0 if ok else 0.0,
            duration_ms=meta.get("duration_ms", 0),
            model_calls=meta.get("provider_requests", 1),
            failure_modes=tuple(modes),
        )

        # Hydra record
        provider_requests = meta.get("provider_requests", 1)
        if isinstance(provider_requests, list):
            provider_requests = len(provider_requests)
        hydra.record_run(
            run_id=run_id, world_genome_id=current_world.id,
            worker_genome_id=f"worker-{profile}", family_id=family_id,
            harness=profile, model=meta.get("model", "mimo-v2.5"),
            cost_usd=meta.get("cost_usd", 0.0),
            duration_ms=meta.get("duration_ms", 0),
            model_calls=provider_requests,
            success=ok, quality_score=fv.quality_score,
            failure_vector=fv, experiment_id=experiment_id,
        )

        # Adversary
        child, strategy, niche = adversary.mutate(current_world, fv)
        score = adversary.objective(fv, child)
        adversary.archive_world(child, fv, score)
        hydra.record_world_genome(child)

        # Stats
        stats[profile]["runs"] += 1
        if ok:
            stats[profile]["success"] += 1
        stats[profile]["total_ms"] += meta.get("duration_ms", 0)
        stats[profile]["qualities"].append(fv.quality_score)

        print(f"  OK: {ok}")
        print(f"  Duration: {meta.get('duration_ms', 0)}ms")
        print(f"  Provider requests: {meta.get('provider_requests', 1)}")
        print(f"  Memory: {meta.get('memory', False)}")
        print(f"  Tools: {meta.get('tools_used', [])}")
        print(f"  Git: {wt.branch}")

    # Report
    print(f"\n{'='*60}")
    print("FOUR-SPEED REPORT")
    print(f"{'='*60}")
    for p in profiles:
        s = stats[p]
        wr = s["success"] / s["runs"] * 100 if s["runs"] else 0
        avg_ms = s["total_ms"] / s["runs"] if s["runs"] else 0
        avg_q = sum(s["qualities"]) / len(s["qualities"]) if s["qualities"] else 0
        print(f"\n  {p:15s} | n={s['runs']:2d} | {wr:5.0f}% | {avg_ms:7.0f}ms | q={avg_q:.2f}")

    summary = hydra.summary()
    print(f"\n  Hydra: {summary['total_runs']} runs, {summary['total_worlds']} worlds")

    results_path = f"/root/mwgym/data/hybrid-{experiment_id}.json"
    Path(results_path).parent.mkdir(parents=True, exist_ok=True)
    Path(results_path).write_text(json.dumps({
        "experiment_id": experiment_id, "family_id": family_id,
        "profiles": profiles, "n_rounds": n_rounds, "stats": stats,
    }, indent=2))
    print(f"  Saved: {results_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=12)
    parser.add_argument("--family", default="compute.routing")
    parser.add_argument("--profiles", default="DIRECT,BOUNDED,STATEFUL_FAST,AGENTIC")
    parser.add_argument("--budget", type=float, default=0.02)
    args = parser.parse_args()
    run_hybrid_loop(
        n_rounds=args.rounds, family_id=args.family,
        profiles=args.profiles.split(","), budget_per_round=args.budget,
    )
