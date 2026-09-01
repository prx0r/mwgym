"""Deterministic Verifier — sovereign truth for WorkerRun evaluation.

No LLM judges. Real tests against the actual code output.
Produces GateResult[] → CapabilityScore[] → FailureVector.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from .spec import GateResult, CapabilityScore, FailureVector, Evaluation


# ─── Verifier Registry ─────────────────────────────────────────────────

_VERIFIERS: dict[str, callable] = {}


def register_verifier(task_id: str):
    """Decorator to register a verifier for a task."""
    def wrapper(fn):
        _VERIFIERS[task_id] = fn
        return fn
    return wrapper


def get_verifier(task_id: str) -> callable | None:
    return _VERIFIERS.get(task_id)


def list_verifiers() -> list[str]:
    return list(_VERIFIERS.keys())


# ─── Runner ─────────────────────────────────────────────────────────────

def _run_python(code: str, cwd: str, timeout: int = 10) -> tuple[bool, str]:
    """Run Python code in a workspace. Returns (ok, output)."""
    try:
        r = subprocess.run(
            [sys.executable, "-c", code],
            cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        output = r.stdout + r.stderr
        return r.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


# ─── Rate Limiter Verifier ─────────────────────────────────────────────

@register_verifier("rate-limiter")
def verify_rate_limiter(workspace: str) -> Evaluation:
    """Deterministic verification for the rate-limiter task."""
    gates = []
    capabilities = []

    # Gate 0: Import check
    ok, out = _run_python(
        "import sys; sys.path.insert(0, '.'); from rate_limiter import RateLimiter",
        workspace
    )
    gates.append(GateResult(
        gate_id="syntax", gate_name="import_check",
        passed=ok, actual=out[:200] if ok else out[:200],
    ))

    if not ok:
        return Evaluation(
            success=False, quality=0.0, gates=gates,
            capabilities=[CapabilityScore("code.write", 0.0, "import failed")],
            failure_vector=FailureVector(modes=["import_error"], severity=1.0),
        )

    # Gate 1: Basic construction
    ok, out = _run_python(textwrap.dedent("""\
        import sys; sys.path.insert(0, '.')
        from rate_limiter import RateLimiter
        rl = RateLimiter(rate=10, burst=5)
        assert hasattr(rl, 'allow'), "missing allow method"
        assert hasattr(rl, 'tokens_remaining'), "missing tokens_remaining method"
        print("OK")
    """), workspace)
    gates.append(GateResult(
        gate_id="api", gate_name="api_surface",
        passed=ok, actual=out[:200],
    ))

    # Gate 2: Basic allow behavior
    ok, out = _run_python(textwrap.dedent("""\
        import sys; sys.path.insert(0, '.')
        from rate_limiter import RateLimiter
        rl = RateLimiter(rate=100, burst=5)
        assert rl.allow() == True, "first call should succeed"
        remaining = rl.tokens_remaining()
        assert 3.9 < remaining < 4.1, f"expected ~4.0, got {remaining}"
        print("OK")
    """), workspace)
    gates.append(GateResult(
        gate_id="basic", gate_name="basic_behavior",
        passed=ok, actual=out[:200],
    ))

    # Gate 3: Burst exhaustion
    ok, out = _run_python(textwrap.dedent("""\
        import sys; sys.path.insert(0, '.')
        from rate_limiter import RateLimiter
        rl = RateLimiter(rate=100, burst=5)
        for _ in range(5):
            rl.allow()
        assert rl.allow() == False, "should be False after burst exhausted"
        remaining = rl.tokens_remaining()
        assert -0.1 < remaining < 0.1, f"expected ~0, got {remaining}"
        print("OK")
    """), workspace)
    gates.append(GateResult(
        gate_id="burst", gate_name="burst_exhaustion",
        passed=ok, actual=out[:200],
    ))

    # Gate 4: Thread safety — use low rate so refill during test is negligible
    ok, out = _run_python(textwrap.dedent("""\
        import sys, threading, time; sys.path.insert(0, '.')
        from rate_limiter import RateLimiter
        rl = RateLimiter(rate=0.001, burst=100)  # very low rate, no refill during test
        results = []
        def worker():
            for _ in range(50):
                results.append(rl.allow())
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(results) == 500, f"expected 500, got {len(results)}"
        true_count = sum(1 for r in results if r)
        assert true_count <= 100, f"allowed {true_count} > burst 100"
        print("OK")
    """), workspace)
    gates.append(GateResult(
        gate_id="thread", gate_name="thread_safety",
        passed=ok, actual=out[:200],
    ))

    # Gate 5: Boundary — rate=0.001, burst=1 (no refill during test)
    ok, out = _run_python(textwrap.dedent("""\
        import sys; sys.path.insert(0, '.')
        from rate_limiter import RateLimiter
        rl = RateLimiter(rate=0.001, burst=1)
        assert rl.allow() == True
        assert rl.allow() == False
        print("OK")
    """), workspace)
    gates.append(GateResult(
        gate_id="boundary", gate_name="boundary_conditions",
        passed=ok, actual=out[:200],
    ))

    # Gate 6: No external imports
    ok, out = _run_python(textwrap.dedent("""\
        import sys, ast; sys.path.insert(0, '.')
        tree = ast.parse(open('rate_limiter.py').read())
        external = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split('.')[0] not in ('threading', 'time'):
                        external.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split('.')[0] not in ('threading', 'time'):
                    external.append(node.module)
        assert not external, f"external imports: {external}"
        print("OK")
    """), workspace)
    gates.append(GateResult(
        gate_id="stdlib", gate_name="stdlib_only",
        passed=ok, actual=out[:200],
    ))

    # Compute scores
    passed_gates = [g for g in gates if g.passed]
    total = len(gates)
    passed_count = len(passed_gates)

    # Capability scores
    write_score = passed_count / total if total > 0 else 0.0
    understand_score = 1.0 if any(g.gate_id == "api" and g.passed for g in gates) else 0.0
    debug_score = passed_count / total if total > 0 else 0.0
    verify_score = 1.0 if passed_count == total else 0.5

    capabilities = [
        CapabilityScore("code.write", write_score, f"{passed_count}/{total} gates"),
        CapabilityScore("code.understand", understand_score, "API surface correct"),
        CapabilityScore("code.debug", debug_score, f"boundary={'pass' if any(g.gate_id=='boundary' and g.passed for g in gates) else 'fail'}"),
        CapabilityScore("process.verify", verify_score, f"{passed_count}/{total} verified"),
    ]

    # Failure modes
    modes = []
    severity = 0.0
    for g in gates:
        if not g.passed:
            modes.append(g.gate_name)
            severity += 0.2 if g.severity == "error" else 0.1
    severity = min(severity, 1.0)

    quality = passed_count / total if total > 0 else 0.0

    return Evaluation(
        success=passed_count == total,
        quality=quality,
        correctness=write_score,
        completeness=quality,
        gates=gates,
        capabilities=capabilities,
        failure_vector=FailureVector(modes=modes, severity=severity),
    )


# ─── Generic Verifier (fallback) ───────────────────────────────────────

@register_verifier("generic")
def verify_generic(workspace: str, task_id: str = "generic",
                   verify_code: str = "") -> Evaluation:
    """Generic verifier — runs a test script if provided."""
    if not verify_code:
        return Evaluation(
            success=True, quality=0.5,
            gates=[GateResult("none", "no_verifier", True, "skipped")],
            capabilities=[CapabilityScore("code.write", 0.5, "unverified")],
        )

    ok, out = _run_python(verify_code, workspace)
    gate = GateResult("test", "test_assertions", passed=ok, actual=out[:300])
    return Evaluation(
        success=ok,
        quality=1.0 if ok else 0.0,
        gates=[gate],
        capabilities=[CapabilityScore("code.write", 1.0 if ok else 0.0, out[:100])],
        failure_vector=FailureVector(
            modes=[] if ok else ["test_failure"],
            severity=0.0 if ok else 0.8,
        ),
    )


def verify(workspace: str, task_id: str, verify_code: str = "") -> Evaluation:
    """Run the appropriate verifier for a task."""
    vfn = _VERIFIERS.get(task_id)
    if vfn:
        if task_id == "generic":
            return vfn(workspace, task_id, verify_code)
        return vfn(workspace)
    return verify_generic(workspace, task_id, verify_code)
