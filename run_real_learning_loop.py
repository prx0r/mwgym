#!/usr/bin/env python3
"""Real Learning Loop v2 — fixed test assertions, proper module names.

Phases:
  1. BASELINE: Run worker-v1 on 5 training tasks (no experience)
  2. REFLECT: Analyze failures, propose memory/skill changes
  3. CANDIDATE: Run worker-v2 (with learned context) on same training tasks
  4. HELD-OUT: Run both v1 and v2 on 5 held-out tasks (frozen assessor)
  5. COMPARE: v1 vs v2, promote if v2 wins
  6. RECORD: Trajectories, capabilities, graph, insights → Hydra
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path("/root/mwgym")))
sys.path.insert(0, str(Path("/root/workerkit")))

from mwgym.harnesses.pydantic_bats import PydanticBATSHarness, UsageLimits
from mwgym.schema.world import GateResult


# ─── Task Definitions ──────────────────────────────────────────────────

TRAINING_TASKS = [
    {
        "id": "rate-limiter",
        "instruction": Path("/root/mwgym/datasets/submissions-v1/task-001-rate-limiter/instruction.md").read_text(),
        "module": "rate_limiter",
        "verify": """import threading, time, sys
sys.path.insert(0, '.')
from rate_limiter import RateLimiter

rl = RateLimiter(rate=100, burst=5)
assert rl.allow() == True, "first allow should be True"
remaining = rl.tokens_remaining()
assert 3.9 < remaining < 4.1, f"expected ~4.0, got {remaining}"
for _ in range(4):
    rl.allow()
remaining = rl.tokens_remaining()
assert -0.1 < remaining < 0.1, f"expected ~0.0, got {remaining}"
assert rl.allow() == False, "should be False when empty"
# thread safety
results = []
def worker():
    for _ in range(20):
        results.append(rl.allow())
threads = [threading.Thread(target=worker) for _ in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
assert len(results) == 80, f"expected 80 results, got {len(results)}"
print("PASS: rate-limiter")""",
    },
    {
        "id": "json-diff",
        "instruction": Path("/root/mwgym/datasets/submissions-v1/task-002-json-diff/instruction.md").read_text(),
        "module": "json_diff",
        "verify": """import sys, json
sys.path.insert(0, '.')
from json_diff import json_diff

a = {"x": 1, "y": 2}
b = {"x": 1, "y": 3, "z": 4}
d = json_diff(a, b)
assert isinstance(d, dict), f"expected dict, got {type(d)}"
assert d.get("y", {}).get("old") == 2, f"y.old should be 2, got {d.get('y')}"
assert d.get("y", {}).get("new") == 3, f"y.new should be 3, got {d.get('y')}"
assert d.get("z", {}).get("new") == 4, f"z.new should be 4, got {d.get('z')}"
# nested
a2 = {"a": {"b": 1}}
b2 = {"a": {"b": 2}}
d2 = json_diff(a2, b2)
assert d2.get("a.b", {}).get("old") == 1, f"nested diff failed: {d2}"
print("PASS: json-diff")""",
    },
    {
        "id": "lru-cache",
        "instruction": Path("/root/mwgym/datasets/submissions-v1/task-003-lru-cache/instruction.md").read_text(),
        "module": "lru_cache",
        "verify": """import sys, time
sys.path.insert(0, '.')
from lru_cache import LRUCache

c = LRUCache(2, ttl_seconds=10)
c.put("a", 1)
c.put("b", 2)
assert c.get("a") == 1, f"expected 1, got {c.get('a')}"
c.put("c", 3)  # evicts "b"
assert c.get("b") is None, f"expected None, got {c.get('b')}"
assert c.get("c") == 3, f"expected 3, got {c.get('c')}"
assert c.size() == 2, f"expected size 2, got {c.size()}"
# ttl test
c2 = LRUCache(5, ttl_seconds=0.1)
c2.put("x", 10)
time.sleep(0.2)
assert c2.get("x") is None, "expected None after TTL expiry"
print("PASS: lru-cache")""",
    },
    {
        "id": "markdown-table",
        "instruction": Path("/root/mwgym/datasets/submissions-v1/task-004-markdown-table/instruction.md").read_text(),
        "module": "md_table",
        "verify": """import sys
sys.path.insert(0, '.')
from md_table import parse_markdown_table

table = "| Name | Age |\\n|------|-----|\\n| Alice | 30 |\\n| Bob | 25 |"
result = parse_markdown_table(table)
assert len(result) == 2, f"expected 2 rows, got {len(result)}"
assert result[0]["Name"] == "Alice", f"expected Alice, got {result[0]}"
assert result[0]["Age"] == "30", f"expected '30', got {result[0].get('Age')}"
assert result[1]["Name"] == "Bob", f"expected Bob, got {result[1]}"
print("PASS: markdown-table")""",
    },
    {
        "id": "config-merge",
        "instruction": Path("/root/mwgym/datasets/submissions-v1/task-005-config-merge/instruction.md").read_text(),
        "module": "config_merge",
        "verify": """import sys
sys.path.insert(0, '.')
from config_merge import deep_merge

base = {"db": {"host": "localhost", "port": 5432}, "debug": False}
override = {"db": {"port": 5433, "name": "prod"}, "debug": True}
m = deep_merge(base, override)
assert m["db"]["host"] == "localhost", f"db.host should be localhost"
assert m["db"]["port"] == 5433, f"db.port should be 5433"
assert m["db"]["name"] == "prod", f"db.name should be prod"
assert m["debug"] == True, f"debug should be True"
# verify no mutation
assert base["db"]["port"] == 5432, "base should not be mutated"
print("PASS: config-merge")""",
    },
]

HELDOUT_TASKS = [
    {
        "id": "word-count",
        "instruction": "Build a function `word_count(text: str) -> dict` that counts word frequencies. Return {word: count} sorted by count descending. Handle empty strings.",
        "module": "word_count",
        "verify": """import sys
sys.path.insert(0, '.')
from word_count import word_count

r = word_count("the cat sat on the mat the cat")
assert isinstance(r, dict), f"expected dict, got {type(r)}"
assert r.get("the", 0) == 3, f"expected 'the'=3, got {r.get('the')}"
assert r.get("cat", 0) == 2, f"expected 'cat'=2, got {r.get('cat')}"
assert word_count("") == {}, "empty string should return {}"
print("PASS: word-count")""",
    },
    {
        "id": "flatten-dict",
        "instruction": "Build a function `flatten_dict(d: dict, sep: str = '.') -> dict` that flattens a nested dictionary. Example: {\"a\": {\"b\": 1}} -> {\"a.b\": 1}",
        "module": "flatten_dict",
        "verify": """import sys
sys.path.insert(0, '.')
from flatten_dict import flatten_dict

r = flatten_dict({"a": {"b": 1, "c": {"d": 2}}})
assert r.get("a.b") == 1, f"expected a.b=1, got {r.get('a.b')}"
assert r.get("a.c.d") == 2, f"expected a.c.d=2, got {r.get('a.c.d')}"
r2 = flatten_dict({"x": 1}, sep="/")
assert r2.get("x") == 1, f"expected x=1, got {r2.get('x')}"
print("PASS: flatten-dict")""",
    },
    {
        "id": "binary-search",
        "instruction": "Build a function `binary_search(arr: list, target: int) -> int` that returns the index of target in sorted arr, or -1 if not found.",
        "module": "binary_search",
        "verify": """import sys
sys.path.insert(0, '.')
from binary_search import binary_search

assert binary_search([1, 2, 3, 4, 5], 3) == 2, f"expected index 2"
assert binary_search([1, 2, 3, 4, 5], 6) == -1, f"expected -1"
assert binary_search([], 1) == -1, f"expected -1 for empty"
assert binary_search([1], 1) == 0, f"expected index 0"
print("PASS: binary-search")""",
    },
    {
        "id": "matrix-transpose",
        "instruction": "Build a function `transpose(matrix: list[list]) -> list[list]` that transposes a matrix. Handle empty and non-rectangular gracefully.",
        "module": "matrix_transpose",
        "verify": """import sys
sys.path.insert(0, '.')
from matrix_transpose import transpose

assert transpose([[1, 2, 3], [4, 5, 6]]) == [[1, 4], [2, 5], [3, 6]]
assert transpose([]) == []
assert transpose([[1]]) == [[1]]
print("PASS: matrix-transpose")""",
    },
    {
        "id": "validate-email",
        "instruction": "Build a function `validate_email(email: str) -> bool` that checks basic email format: has @, has domain, has TLD. No regex needed.",
        "module": "validate_email",
        "verify": """import sys
sys.path.insert(0, '.')
from validate_email import validate_email

assert validate_email("a@b.com") == True
assert validate_email("no-at-sign.com") == False
assert validate_email("@no-local.com") == False
assert validate_email("user@") == False
assert validate_email("") == False
print("PASS: validate-email")""",
    },
]


# ─── Evaluator ──────────────────────────────────────────────────────────

def evaluate_code(workspace: str, verify_code: str) -> tuple[bool, str]:
    """Run test assertions in workspace. Returns (passed, output)."""
    try:
        r = subprocess.run(
            [sys.executable, "-c", verify_code],
            cwd=workspace,
            capture_output=True, text=True, timeout=15,
        )
        output = r.stdout + r.stderr
        passed = r.returncode == 0 and "PASS:" in output
        return passed, output.strip()
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


# ─── Trajectory Recording ──────────────────────────────────────────────

@dataclass
class TrajectoryStep:
    step_type: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    content_preview: str = ""
    metadata: dict = field(default_factory=dict)


def record_trajectory(hydra, run_id: str, steps: list[TrajectoryStep]):
    conn = hydra._conn()
    conn.execute("""
        INSERT OR REPLACE INTO trajectories (run_id, events, created_at)
        VALUES (?, ?, ?)
    """, (run_id, json.dumps([s.__dict__ for s in steps]), time.time()))
    conn.commit()
    conn.close()


# ─── Main Loop ──────────────────────────────────────────────────────────

def run_one_task(harness, task, run_id, ws, worker_id, family_id,
                 hydra, experiment_id, context=""):
    """Run one task, evaluate, record to Hydra. Returns (passed, duration_ms)."""
    os.makedirs(ws, exist_ok=True)

    task_msg = task["instruction"]
    if context:
        task_msg = f"Lessons from experience:\n{context}\n\n{task_msg}"

    run_obj, fv = harness.run(
        task=task_msg,
        workspace=ws,
        limits=UsageLimits(request_limit=1, cost_limit_usd=0.01, wall_time_limit_s=30),
        world_genome_id="learning-loop",
        worker_genome_id=worker_id,
        family_id=family_id,
    )

    passed, eval_output = evaluate_code(ws, task["verify"])

    hydra.record_run(
        run_id=run_id, world_genome_id="learning-loop",
        worker_genome_id=worker_id, family_id=family_id,
        harness="pydantic-bats", model="mimo-v2.5",
        cost_usd=run_obj.cost_usd, duration_ms=run_obj.duration_ms,
        model_calls=len(run_obj.model_calls), success=passed,
        quality_score=1.0 if passed else 0.0, failure_vector=fv,
        experiment_id=experiment_id,
    )
    hydra.record_capability(worker_id, family_id, "code.write", 1.0 if passed else 0.0)

    # Graph
    hydra.add_node(f"run:{run_id}", "Run", {"phase": run_id.split("-")[1]})
    hydra.add_node(f"worker:{worker_id}", "WorkerGenome", {"id": worker_id})
    hydra.add_edge(f"run:{run_id}", f"worker:{worker_id}", "EXECUTED_BY")

    # Trajectory
    traj = [TrajectoryStep(
        step_type="model_call", model=run_obj.metadata.get("model", "mimo-v2.5"),
        input_tokens=run_obj.total_tokens, duration_ms=run_obj.duration_ms,
        content_preview=run_obj.output[:200],
    )]
    record_trajectory(hydra, run_id, traj)

    return passed, run_obj.duration_ms, run_obj.output, eval_output


def run_learning_loop():
    hydra = None  # TODO: Wire real HydraDB client
    harness = PydanticBATSHarness()

    experiment_id = f"learn-{int(time.time())}"
    hydra.record_experiment(
        experiment_id=experiment_id,
        hypothesis="v2 (with learned lessons) outperforms v1 on held-out tasks",
        family_id="submissions-v1",
    )
    hydra.record_worker_genome("v1", harness="pydantic-bats", model="mimo-v2.5")
    hydra.record_worker_genome("v2", harness="pydantic-bats", model="mimo-v2.5")

    # ─── PHASE 1: BASELINE ───────────────────────────────────────

    print("=" * 60)
    print("PHASE 1: BASELINE (worker-v1 on training tasks)")
    print("=" * 60)

    v1_results = []
    v1_outputs = {}
    for task in TRAINING_TASKS:
        run_id = f"v1-train-{task['id']}"
        ws = f"/tmp/mwgym-learn/{run_id}"
        print(f"  {task['id']}...", end=" ", flush=True)
        passed, dur, output, eval_out = run_one_task(
            harness, task, run_id, ws, "v1", task["id"], hydra, experiment_id)
        print(f"{'PASS' if passed else 'FAIL'} ({dur}ms)")
        v1_results.append({"task": task["id"], "passed": passed, "duration_ms": dur})
        v1_outputs[task["id"]] = {"passed": passed, "output": output[:500], "eval": eval_out}

    v1_rate = sum(1 for r in v1_results if r["passed"]) / len(v1_results)
    print(f"\n  V1: {sum(1 for r in v1_results if r['passed'])}/{len(v1_results)} ({v1_rate:.0%})")

    # ─── PHASE 2: REFLECT ────────────────────────────────────────

    print("\n" + "=" * 60)
    print("PHASE 2: REFLECT (analyze failures, propose lessons)")
    print("=" * 60)

    lessons = []
    failed_tasks = [t for t in v1_results if not t["passed"]]
    passed_tasks = [t for t in v1_results if t["passed"]]

    for t in failed_tasks:
        tid = t["task"]
        info = v1_outputs[tid]
        eval_out = info["eval"]

        if "TIMEOUT" in eval_out:
            lessons.append(f"Task {tid}: keep implementation simple, avoid complex logic.")
        elif "ImportError" in eval_out or "ModuleNotFoundError" in eval_out:
            lessons.append(f"Task {tid}: module name must match the filename. Check import paths.")
        elif "AssertionError" in eval_out or "assert" in eval_out.lower():
            # Extract the actual vs expected
            for line in eval_out.split("\n"):
                if "expected" in line.lower() or "should be" in line.lower():
                    lessons.append(f"Task {tid}: {line.strip()}")
                    break
            else:
                lessons.append(f"Task {tid}: output doesn't match expected behavior. Test mentally.")
        elif "Error" in eval_out or "error" in eval_out.lower():
            first_err = [l for l in eval_out.split("\n") if "error" in l.lower() or "Error" in l]
            lessons.append(f"Task {tid}: {first_err[0].strip()[:100] if first_err else 'runtime error'}")
        else:
            lessons.append(f"Task {tid}: review requirements carefully, check function signatures.")

    # Universal lessons
    lessons.append("Always handle edge cases: empty inputs, single elements, boundary conditions.")
    lessons.append("Match the exact function/class names and module names specified in requirements.")
    lessons.append("Use approximate comparisons for floating point (assert abs(val - expected) < 0.01).")

    # Deduplicate
    lessons = list(dict.fromkeys(lessons))

    print(f"  Generated {len(lessons)} lessons:")
    for l in lessons:
        print(f"    - {l}")

    hydra.add_insight(
        insight_id=f"insight-{experiment_id}-reflect",
        title="V1 failure analysis",
        body=json.dumps({"failed": len(failed_tasks), "passed": len(passed_tasks), "lessons": lessons}),
        kind="reflection", experiment_id=experiment_id,
        evidence_runs=len(v1_results), confidence=0.6,
    )

    # ─── PHASE 3: CANDIDATE (v2) ─────────────────────────────────

    print("\n" + "=" * 60)
    print("PHASE 3: CANDIDATE (worker-v2 with lessons on training tasks)")
    print("=" * 60)

    lesson_text = "\n".join(f"- {l}" for l in lessons)
    v2_results = []
    for task in TRAINING_TASKS:
        run_id = f"v2-train-{task['id']}"
        ws = f"/tmp/mwgym-learn/{run_id}"
        print(f"  {task['id']}...", end=" ", flush=True)
        passed, dur, _, _ = run_one_task(
            harness, task, run_id, ws, "v2", task["id"], hydra, experiment_id,
            context=lesson_text)
        print(f"{'PASS' if passed else 'FAIL'} ({dur}ms)")
        v2_results.append({"task": task["id"], "passed": passed, "duration_ms": dur})

    v2_rate = sum(1 for r in v2_results if r["passed"]) / len(v2_results)
    print(f"\n  V2: {sum(1 for r in v2_results if r['passed'])}/{len(v2_results)} ({v2_rate:.0%})")

    # ─── PHASE 4: HELD-OUT ──────────────────────────────────────

    print("\n" + "=" * 60)
    print("PHASE 4: HELD-OUT (v1 vs v2 on unseen tasks)")
    print("=" * 60)

    v1_heldout = []
    v2_heldout = []
    for task in HELDOUT_TASKS:
        print(f"\n  {task['id']}:")
        # V1
        run_id = f"v1-ho-{task['id']}"
        ws = f"/tmp/mwgym-learn/{run_id}"
        passed_v1, dur_v1, _, _ = run_one_task(
            harness, task, run_id, ws, "v1", task["id"], hydra, experiment_id)
        print(f"    V1: {'PASS' if passed_v1 else 'FAIL'} ({dur_v1}ms)")
        v1_heldout.append({"task": task["id"], "passed": passed_v1})

        # V2
        run_id = f"v2-ho-{task['id']}"
        ws = f"/tmp/mwgym-learn/{run_id}"
        passed_v2, dur_v2, _, _ = run_one_task(
            harness, task, run_id, ws, "v2", task["id"], hydra, experiment_id,
            context=lesson_text)
        print(f"    V2: {'PASS' if passed_v2 else 'FAIL'} ({dur_v2}ms)")
        v2_heldout.append({"task": task["id"], "passed": passed_v2})

        # Comparison edge
        hydra.add_edge(f"run:v1-ho-{task['id']}", f"run:v2-ho-{task['id']}", "HELDOUT_CMP")

    # ─── PHASE 5: PROMOTE ───────────────────────────────────────

    print("\n" + "=" * 60)
    print("PHASE 5: COMPARISON")
    print("=" * 60)

    v1_ho_pass = sum(1 for r in v1_heldout if r["passed"])
    v2_ho_pass = sum(1 for r in v2_heldout if r["passed"])
    v1_ho_rate = v1_ho_pass / len(v1_heldout)
    v2_ho_rate = v2_ho_pass / len(v2_heldout)
    promoted = v2_ho_rate > v1_ho_rate

    print(f"  Training:  V1={sum(1 for r in v1_results if r['passed'])}/{len(v1_results)}  V2={sum(1 for r in v2_results if r['passed'])}/{len(v2_results)}")
    print(f"  Held-out:  V1={v1_ho_pass}/{len(v1_heldout)} ({v1_ho_rate:.0%})  V2={v2_ho_pass}/{len(v2_heldout)} ({v2_ho_rate:.0%})")
    print(f"  Delta:     {(v2_ho_rate - v1_ho_rate):+.0%}")
    print(f"  PROMOTED:  {'YES' if promoted else 'NO'}")

    hydra.add_insight(
        insight_id=f"insight-{experiment_id}-promo",
        title="V1 vs V2 held-out comparison",
        body=json.dumps({
            "v1_heldout": v1_ho_rate, "v2_heldout": v2_ho_rate,
            "delta": v2_ho_rate - v1_ho_rate, "promoted": promoted,
            "lessons": lessons,
        }),
        kind="promotion", experiment_id=experiment_id,
        evidence_runs=len(v1_heldout) + len(v2_heldout),
        confidence=abs(v2_ho_rate - v1_ho_rate),
    )

    if promoted:
        hydra.record_worker_genome("v2-promoted", parent_id="v1", generation=1,
                                    harness="pydantic-bats", model="mimo-v2.5",
                                    config={"lessons": lessons})
        hydra.add_node("worker:v2-promoted", "WorkerGenome", {"promoted": True, "gen": 1})
        hydra.add_edge("worker:v2-promoted", "worker:v1", "EVOLVED_FROM")

    hydra.complete_experiment(experiment_id, results={
        "v1_heldout": v1_ho_rate, "v2_heldout": v2_ho_rate,
        "promoted": promoted, "lessons": lessons,
    })

    # ─── FINAL STATE ─────────────────────────────────────────────

    print("\n" + "=" * 60)
    print("HYDRA STATE")
    print("=" * 60)
    s = hydra.summary()
    print(f"  Runs: {s['total_runs']}  Workers: {s['total_workers']}  Experiments: {s['total_experiments']}")
    caps_v1 = hydra.get_capabilities("v1")
    caps_v2 = hydra.get_capabilities("v2")
    print(f"  Capabilities: v1={len(caps_v1)} v2={len(caps_v2)}")
    conn = hydra._conn()
    trajs = conn.execute("SELECT COUNT(*) FROM trajectories").fetchone()[0]
    nodes = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
    edges = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
    insights = conn.execute("SELECT COUNT(*) FROM insights").fetchone()[0]
    conn.close()
    print(f"  Trajectories: {trajs}  Graph: {nodes} nodes, {edges} edges  Insights: {insights}")

    return {"experiment_id": experiment_id, "v1_heldout": v1_ho_rate,
            "v2_heldout": v2_ho_rate, "promoted": promoted, "lessons": lessons}


if __name__ == "__main__":
    result = run_learning_loop()
    print(json.dumps(result, indent=2))
