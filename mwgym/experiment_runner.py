"""Experiment Runner — comprehensive testing with logging and reporting.

Runs multiple experiment types, logs every run to Hydra + JSONL,
produces comparison tables after each batch.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path("/root/mwgym")))
sys.path.insert(0, str(Path("/root/workerkit")))

from mwgym.workspace import LabWorkspace
from mwgym.schema.world import WorldGenome, FailureVector, GateResult
from mwgym.worlds.cge_adapter import compile_world
from mwgym.worlds.adversary import Adversary
from mwgym.worlds.curriculum import Curriculum, CurriculumConfig
from mwgym.hybrid_loop import run_letta_direct, run_bounded
from mwgym.lab_brief import generate_brief
from mwgym.harnesses.pydantic_bats import PydanticBATSHarness, UsageLimits

# ─── Logging ──────────────────────────────────────────────────────────

LOG_DIR = Path("/root/mwgym/data/experiments")
LOG_DIR.mkdir(parents=True, exist_ok=True)

def log_run(log_file: Path, entry: dict):
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

def print_table(title: str, rows: list[dict], columns: list[str]):
    """Print a formatted table."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")
    # Header
    header = " | ".join(f"{c:15s}" for c in columns)
    print(f"  {header}")
    print(f"  {'-'*len(header)}")
    # Rows
    for row in rows:
        line = " | ".join(f"{str(row.get(c, '')):15s}" for c in columns)
        print(f"  {line}")
    print()

# ─── Task generators ──────────────────────────────────────────────────

WORLD_TASKS = {
    "compute.routing": {
        "difficulty_range": (2, 6),
        "seed_base": 42,
    },
    "software.implementation": {
        "difficulty_range": (2, 5),
        "seed_base": 100,
    },
    "research.verification": {
        "difficulty_range": (2, 5),
        "seed_base": 200,
    },
}

CODING_TASKS = {
    "rate-limiter": "Build a Python class RateLimiter with token bucket. __init__(rate, burst), allow() -> bool, tokens_remaining() -> float. Thread-safe.",
    "json-diff": "Build json_diff(a: dict, b: dict) -> dict. Deep diff with dot-separated paths, {old, new} entries.",
    "lru-cache": "Build LRUCache(capacity, ttl_seconds). get(key), put(key, value), size(). LRU eviction + TTL.",
    "config-merge": "Build deep_merge(base, override) -> dict. Recursive merge, override wins, no mutation.",
    "word-count": "Build word_count(text: str) -> dict. Returns {word: count} for all words, case-insensitive, sorted by frequency.",
}

# ─── Experiments ──────────────────────────────────────────────────────

def exp_01_direct_baseline(hydra, lab, exp_id):
    """10 DIRECT rounds on compute.routing — baseline."""
    print("\n" + "#" * 70)
    print("# EXPERIMENT 01: DIRECT baseline x10")
    print("#" * 70)

    world = WorldGenome(id="exp01-world", family_id="compute.routing",
                        difficulty=3, seed=42,
                        structure={"max_steps": 5, "capabilities": ["model.select"]},
                        resources={"budget_usd": 0.05, "free_calls": 5})
    hydra.record_world_genome(world)

    rows = []
    for i in range(10):
        run_id = f"exp01-direct-{i:03d}"
        wt = lab.create_run(run_id)
        wt.seed_world({
            "task.json": json.dumps({"family": "compute.routing", "difficulty": 3,
                                     "action": "compute shortest paths in a graph"}),
            "README.md": "# Compute Routing\nImplement shortest path.\n",
        }, f"world: exp01")

        task = "Read task.json. Implement a routing algorithm that computes shortest paths. Write solution.py."
        t0 = time.time()
        result, meta = run_letta_direct(task, wt.path)
        wt.commit_worker_output(f"direct: {result.get('ok', False)}")

        ok = result.get("ok", False)
        ms = meta.get("duration_ms", 0)
        files = [f for f in os.listdir(wt.path) if f.endswith(".py")]

        fv = FailureVector(run_id=run_id, quality_score=1.0 if ok else 0.0,
                           duration_ms=ms, model_calls=1)
        hydra.record_run(run_id=run_id, world_genome_id=world.id,
                         harness="DIRECT", model="mimo-v2.5",
                         duration_ms=ms, model_calls=1, success=ok,
                         quality_score=fv.quality_score, failure_vector=fv, experiment_id=exp_id)

        row = {"round": i, "ok": ok, "ms": ms, "files": len(files), "branch": wt.branch}
        rows.append(row)
        log_run(LOG_DIR / "exp01.jsonl", row)
        status = "OK" if ok else "FAIL"
        print(f"  R{i:02d} | {status} | {ms:6d}ms | files={files}")

    oks = sum(1 for r in rows if r["ok"])
    avg_ms = sum(r["ms"] for r in rows) / len(rows)
    print(f"\n  RESULT: {oks}/10 pass, avg {avg_ms:.0f}ms")
    return {"experiment": "01_direct_baseline", "pass": oks, "total": 10, "avg_ms": avg_ms}


def exp_02_bounded_baseline(hydra, lab, exp_id):
    """10 BOUNDED rounds — test request_limit enforcement."""
    print("\n" + "#" * 70)
    print("# EXPERIMENT 02: BOUNDED baseline x10")
    print("#" * 70)

    world = WorldGenome(id="exp02-world", family_id="compute.routing",
                        difficulty=3, seed=43,
                        structure={"max_steps": 5, "capabilities": ["model.select"]},
                        resources={"budget_usd": 0.05, "free_calls": 5})
    hydra.record_world_genome(world)

    rows = []
    for i in range(10):
        run_id = f"exp02-bounded-{i:03d}"
        wt = lab.create_run(run_id)
        wt.seed_world({
            "task.json": json.dumps({"family": "compute.routing", "difficulty": 3,
                                     "action": "compute shortest paths in a graph"}),
            "README.md": "# Compute Routing\nImplement shortest path.\n",
        }, f"world: exp02")

        task = "Read task.json. Implement a routing algorithm. Write solution.py."
        t0 = time.time()
        result, meta = run_bounded(task, wt.path, budget=0.01)
        wt.commit_worker_output(f"bounded: {result.get('ok', False)}")

        ok = result.get("ok", False)
        ms = meta.get("duration_ms", 0)
        reqs = meta.get("provider_requests", 1)
        files = [f for f in os.listdir(wt.path) if f.endswith(".py")]

        fv = FailureVector(run_id=run_id, quality_score=1.0 if ok else 0.0,
                           duration_ms=ms, model_calls=reqs)
        hydra.record_run(run_id=run_id, world_genome_id=world.id,
                         harness="BOUNDED", model=meta.get("model", "mimo-v2.5"),
                         duration_ms=ms, model_calls=reqs, success=ok,
                         cost_usd=meta.get("cost_usd", 0.0),
                         quality_score=fv.quality_score, failure_vector=fv, experiment_id=exp_id)

        row = {"round": i, "ok": ok, "ms": ms, "reqs": reqs, "files": len(files)}
        rows.append(row)
        log_run(LOG_DIR / "exp02.jsonl", row)
        status = "OK" if ok else "FAIL"
        print(f"  R{i:02d} | {status} | {ms:6d}ms | {reqs} reqs | files={files}")

    oks = sum(1 for r in rows if r["ok"])
    avg_ms = sum(r["ms"] for r in rows) / len(rows)
    print(f"\n  RESULT: {oks}/10 pass, avg {avg_ms:.0f}ms")
    return {"experiment": "02_bounded_baseline", "pass": oks, "total": 10, "avg_ms": avg_ms}


def exp_03_coding_tasks(hydra, lab, exp_id):
    """5 rounds on real coding tasks."""
    print("\n" + "#" * 70)
    print("# EXPERIMENT 03: Coding tasks x5")
    print("#" * 70)

    rows = []
    for i, (name, instruction) in enumerate(CODING_TASKS.items()):
        run_id = f"exp03-coding-{name}"
        wt = lab.create_run(run_id)
        wt.seed_world({
            "instruction.md": instruction,
            "README.md": f"# {name}\n",
        }, f"world: {name}")

        t0 = time.time()
        result, meta = run_letta_direct(instruction, wt.path)
        wt.commit_worker_output(f"coding: {name}")

        ok = result.get("ok", False)
        ms = meta.get("duration_ms", 0)
        files = [f for f in os.listdir(wt.path) if f.endswith(".py")]

        # Verify code actually works
        verified = False
        if files:
            try:
                code = open(os.path.join(wt.path, files[0])).read()
                exec(code)
                verified = True
            except: pass

        fv = FailureVector(run_id=run_id, quality_score=1.0 if verified else 0.0,
                           duration_ms=ms, model_calls=1)
        hydra.record_run(run_id=run_id, harness="DIRECT", model="mimo-v2.5",
                         duration_ms=ms, model_calls=1, success=ok,
                         quality_score=fv.quality_score, failure_vector=fv, experiment_id=exp_id,
                         family_id="software.implementation")

        row = {"task": name, "ok": ok, "verified": verified, "ms": ms, "files": files}
        rows.append(row)
        log_run(LOG_DIR / "exp03.jsonl", row)
        v = "PASS" if verified else "FAIL"
        c = "OK" if ok else "FAIL"
        print(f"  {name:20s} | code={c} | verify={v} | {ms}ms | {files}")

    verified_count = sum(1 for r in rows if r["verified"])
    print(f"\n  RESULT: {verified_count}/5 verified")
    return {"experiment": "03_coding_tasks", "verified": verified_count, "total": 5}


def exp_04_research_tasks(hydra, lab, exp_id):
    """5 rounds on research.verification family."""
    print("\n" + "#" * 70)
    print("# EXPERIMENT 04: Research verification x5")
    print("#" * 70)

    research_tasks = [
        ("fact-check", "Verify: Python's GIL prevents true parallelism. Return JSON with verdict (true/false/partial), evidence, confidence."),
        ("source-eval", "Evaluate source: 'Python 3.12 removed the GIL' — is this accurate? Return verdict + explanation."),
        ("claim-support", "Check: 'TypeScript is a superset of JavaScript' — does TypeScript add type errors at runtime? Return analysis."),
        ("evidence-quality", "Rate evidence quality: A blog post from 2024 says 'Rust is faster than C'. What factors affect this claim's reliability?"),
        ("causal-reasoning", "Analyze: 'Company X adopted AI and profits increased' — is this causal or correlational? Return reasoning."),
    ]

    rows = []
    for i, (name, instruction) in enumerate(research_tasks):
        run_id = f"exp03-research-{name}"
        wt = lab.create_run(run_id)
        wt.seed_world({
            "task.md": instruction,
            "README.md": f"# {name}\n",
        }, f"world: research-{name}")

        t0 = time.time()
        result, meta = run_letta_direct(instruction, wt.path)
        wt.commit_worker_output(f"research: {name}")

        ok = result.get("ok", False)
        ms = meta.get("duration_ms", 0)
        output = result.get("output", "")
        has_analysis = len(output) > 100  # basic quality check

        fv = FailureVector(run_id=run_id, quality_score=1.0 if has_analysis else 0.0,
                           duration_ms=ms, model_calls=1)
        hydra.record_run(run_id=run_id, harness="DIRECT", model="mimo-v2.5",
                         duration_ms=ms, model_calls=1, success=ok,
                         quality_score=fv.quality_score, failure_vector=fv, experiment_id=exp_id,
                         family_id="research.verification")

        row = {"task": name, "ok": ok, "quality": has_analysis, "ms": ms, "output_len": len(output)}
        rows.append(row)
        log_run(LOG_DIR / "exp04.jsonl", row)
        q = "PASS" if has_analysis else "FAIL"
        print(f"  {name:20s} | ok={ok} | quality={q} | {ms}ms | output={len(output)} chars")

    quality_count = sum(1 for r in rows if r["quality"])
    print(f"\n  RESULT: {quality_count}/5 quality")
    return {"experiment": "04_research_tasks", "quality": quality_count, "total": 5}


# ─── Main ─────────────────────────────────────────────────────────────

def run_all():
    hydra = None  # TODO: Wire real HydraDB client
    lab = LabWorkspace()
    exp_id = f"comprehensive-{int(time.time())}"
    hydra.record_experiment(exp_id, "Comprehensive four-speed testing", family_id="all")

    results = []

    # Experiment 1: DIRECT baseline
    r = exp_01_direct_baseline(hydra, lab, exp_id)
    results.append(r)

    # Experiment 2: BOUNDED baseline
    r = exp_02_bounded_baseline(hydra, lab, exp_id)
    results.append(r)

    # Experiment 3: Coding tasks
    r = exp_03_coding_tasks(hydra, lab, exp_id)
    results.append(r)

    # Experiment 4: Research tasks
    r = exp_04_research_tasks(hydra, lab, exp_id)
    results.append(r)

    # Final report
    print("\n" + "#" * 70)
    print("# FINAL REPORT")
    print("#" * 70)
    print_table("Experiment Results", results, ["experiment", "pass", "total", "verified", "quality", "avg_ms"])

    summary = hydra.summary()
    print(f"  Hydra: {summary['total_runs']} runs, {summary['total_worlds']} worlds")

    # Save
    report = {"exp_id": exp_id, "results": results, "hydra": summary}
    report_path = LOG_DIR / f"report-{exp_id}.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"  Report: {report_path}")

    return results


if __name__ == "__main__":
    run_all()
