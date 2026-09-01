"""CGE Adapter — compiles WorldGenome into executable CG worlds.

Implements the CG kernel interface:
  reset() → State
  observe(state) → dict
  actions(state) → tuple[ActionSpec]
  apply(state, action, result) → State
  terminal(state) → bool
  score(state) → MetricVector

Also produces FailureVector from a completed run.

This is the bridge between CGE's adversarial curriculum and CG's
deterministic world runtime.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Any

from ..schema.world import (
    CapabilityScore, FailureVector, GateResult, WorldGenome,
)


# ─── CG-style contracts (minimal, local) ─────────────────────────────

@dataclass(frozen=True)
class ActionSpec:
    kind: str
    payload: dict = field(default_factory=dict)
    estimated_cost: float = 0.0

    @property
    def action_id(self) -> str:
        return hashlib.sha256(
            json.dumps({"kind": self.kind, "payload": self.payload},
                       sort_keys=True).encode()
        ).hexdigest()[:12]


@dataclass(frozen=True)
class ActionResult:
    action_id: str = ""
    status: str = "ok"         # ok, error, timeout
    payload: dict = field(default_factory=dict)
    cash_cost: float = 0.0
    error: str | None = None


@dataclass(frozen=True)
class Metric:
    name: str
    value: float
    direction: str = "max"     # min or max


@dataclass(frozen=True)
class MetricVector:
    metrics: tuple[Metric, ...] = ()

    def get(self, name: str) -> float | None:
        return next((m.value for m in self.metrics if m.name == name), None)


# ─── World State ──────────────────────────────────────────────────────

@dataclass
class WorldState:
    """Mutable state for an executable world."""
    world_genome_id: str = ""
    seed: int = 0
    step: int = 0
    max_steps: int = 10
    terminal: bool = False

    # Hidden truth (worker never sees this directly)
    hidden: dict = field(default_factory=dict)

    # Observable state (what the worker sees)
    observable: dict = field(default_factory=dict)

    # Available actions at this step
    available_actions: list[dict] = field(default_factory=list)

    # History of actions taken
    action_history: list[dict] = field(default_factory=list)

    # Costs accumulated
    total_cost_usd: float = 0.0
    model_calls: int = 0
    tool_calls: int = 0

    # Quality tracking
    correctness: float = 0.0
    completeness: float = 0.0
    evidence_quality: float = 0.0


# ─── Base World ───────────────────────────────────────────────────────

class BaseWorld:
    """Base class for CG-compiled worlds.

    Subclass this for each family. The compile() classmethod creates
    a BaseWorld from a WorldGenome.
    """

    def __init__(self, genome: WorldGenome):
        self.genome = genome
        self._rng = random.Random(genome.seed)

    def reset(self, instance_id: str = "", seed: int = 0) -> WorldState:
        """Initialize world state from genome."""
        rng = random.Random(seed or self.genome.seed)
        state = WorldState(
            world_genome_id=self.genome.id,
            seed=seed or self.genome.seed,
            max_steps=self.genome.structure.get("max_steps", 10),
        )

        # Generate hidden truth based on family
        state.hidden = self._generate_truth(rng)
        state.observable = self._generate_observable(rng, state.hidden)
        state.available_actions = self._generate_actions(state)

        return state

    def observe(self, state: WorldState) -> dict:
        """What the worker can see."""
        return {
            "step": state.step,
            "observable": state.observable,
            "available_actions": state.available_actions,
            "total_cost_usd": state.total_cost_usd,
            "action_history": state.action_history[-5:],  # last 5
        }

    def actions(self, state: WorldState) -> list[ActionSpec]:
        """Available actions at this state."""
        return [
            ActionSpec(kind=a["kind"], payload=a.get("payload", {}),
                       estimated_cost=a.get("estimated_cost", 0.0))
            for a in state.available_actions
        ]

    def apply(self, state: WorldState, action: ActionSpec,
              result: ActionResult) -> WorldState:
        """Apply action result to state. Returns new state."""
        new_state = WorldState(
            world_genome_id=state.world_genome_id,
            seed=state.seed,
            step=state.step + 1,
            max_steps=state.max_steps,
            hidden=state.hidden,
            observable=dict(state.observable),
            available_actions=[],
            action_history=state.action_history + [{
                "step": state.step,
                "action": action.kind,
                "status": result.status,
                "cost": result.cash_cost,
            }],
            total_cost_usd=state.total_cost_usd + result.cash_cost,
            model_calls=state.model_calls,
            tool_calls=state.tool_calls,
            correctness=state.correctness,
            completeness=state.completeness,
            evidence_quality=state.evidence_quality,
        )

        # Update observable based on action
        if result.status == "ok":
            self._process_result(new_state, action, result)

        # Check termination
        if new_state.step >= new_state.max_steps:
            new_state.terminal = True

        # Generate next actions
        new_state.available_actions = self._generate_actions(new_state)

        return new_state

    def terminal(self, state: WorldState) -> bool:
        return state.terminal

    def score(self, state: WorldState) -> MetricVector:
        """Score the world. Subclass for family-specific scoring."""
        correct = 1.0 if state.correctness >= 0.8 else 0.0
        return MetricVector(metrics=(
            Metric("correct", correct, "max"),
            Metric("quality", state.correctness, "max"),
            Metric("completeness", state.completeness, "max"),
            Metric("evidence_quality", state.evidence_quality, "max"),
            Metric("cash_cost", state.total_cost_usd, "min"),
            Metric("model_calls", float(state.model_calls), "min"),
        ))

    def to_failure_vector(self, state: WorldState,
                           worker_genome_id: str = "") -> FailureVector:
        """Convert completed world state to FailureVector."""
        metrics = self.score(state)
        quality = metrics.get("quality") or 0.0
        completeness = metrics.get("completeness") or 0.0

        # Determine gate results
        gates = self._evaluate_gates(state)
        gates_passed = sum(1 for g in gates if g.passed)

        # Detect failure modes
        failure_modes = self._detect_failure_modes(state)

        # Capability scores
        capabilities = self._score_capabilities(state)

        return FailureVector(
            run_id=f"run-{state.seed}-{state.step}",
            world_genome_id=state.world_genome_id,
            worker_genome_id=worker_genome_id,
            gates=tuple(gates),
            gates_passed=gates_passed,
            gates_total=len(gates),
            capabilities=tuple(capabilities),
            failure_modes=tuple(failure_modes),
            quality_score=quality,
            correctness=state.correctness,
            completeness=completeness,
            efficiency=1.0 - min(1.0, state.total_cost_usd / max(0.01, self.genome.resources.get("budget_usd", 1.0))),
            duration_ms=state.step * 1000,  # estimate
            model_calls=state.model_calls,
            tool_calls=state.tool_calls,
        )

    # ─── Hooks for subclasses ──────────────────────────────────────────

    def _generate_truth(self, rng: random.Random) -> dict:
        """Generate hidden canonical state. Override per family."""
        return {"answer": rng.choice(["A", "B", "C", "D"])}

    def _generate_observable(self, rng: random.Random, hidden: dict) -> dict:
        """Generate what the worker sees. Override per family."""
        info = self.genome.information
        noise = info.get("noise_level", 0.1)
        return {
            "hint": hidden["answer"],
            "confidence": 1.0 - noise,
        }

    def _generate_actions(self, state: WorldState) -> list[dict]:
        """Generate available actions. Override per family."""
        if state.terminal:
            return []
        return [
            {"kind": "ANSWER", "payload": {"answer": "A"}, "estimated_cost": 0.0},
            {"kind": "ANSWER", "payload": {"answer": "B"}, "estimated_cost": 0.0},
            {"kind": "ANSWER", "payload": {"answer": "C"}, "estimated_cost": 0.0},
            {"kind": "ANSWER", "payload": {"answer": "D"}, "estimated_cost": 0.0},
        ]

    def _process_result(self, state: WorldState, action: ActionSpec,
                         result: ActionResult):
        """Update state based on action result. Override per family."""
        if action.kind == "ANSWER":
            answer = action.payload.get("answer", "")
            state.correctness = 1.0 if answer == state.hidden.get("answer") else 0.0
            state.terminal = True

    def _evaluate_gates(self, state: WorldState) -> list[GateResult]:
        """Evaluate hard gates. Override per family."""
        return [
            GateResult(
                gate_id="g0", gate_name="answered",
                passed=state.correctness > 0,
                expected="non-zero correctness",
                actual=str(state.correctness),
            ),
        ]

    def _detect_failure_modes(self, state: WorldState) -> list[str]:
        """Detect specific failure modes. Override per family."""
        modes = []
        if state.correctness < 0.5:
            modes.append("incorrect_answer")
        if state.total_cost_usd > self.genome.resources.get("budget_usd", 1.0) * 0.9:
            modes.append("budget_exceeded")
        if state.step >= state.max_steps:
            modes.append("step_limit_reached")
        return modes

    def _score_capabilities(self, state: WorldState) -> list[CapabilityScore]:
        """Score capability dimensions. Override per family."""
        caps = self.genome.structure.get("capabilities", [])
        if not caps:
            caps = ["reasoning.default"]
        return [
            CapabilityScore(capability=c, score=state.correctness, n_samples=1, confidence=0.5)
            for c in caps
        ]


# ─── Family-Specific Worlds ──────────────────────────────────────────

class SoftwareBugFixWorld(BaseWorld):
    """Software bug fix world: hidden bug, observable symptoms."""

    def _generate_truth(self, rng):
        bugs = ["off_by_one", "null_ref", "logic_error", "race_condition", "memory_leak"]
        return {
            "bug_type": rng.choice(bugs),
            "file": f"src/module_{rng.randint(1,5)}.py",
            "line": rng.randint(10, 200),
            "fix_description": "Apply the correct fix for the detected bug type.",
        }

    def _generate_observable(self, rng, hidden):
        info = self.genome.information
        distractors = info.get("distractors", 0.2)
        stale = info.get("stale_sources", 0.1)

        return {
            "symptoms": [f"Error in {hidden['file']}"],
            "test_output": f"FAILED: test_{hidden['bug_type']}",
            "distractor_files": [f"unrelated_file_{i}.py" for i in range(int(distractors * 10))],
            "stale_docs": stale > 0.1,
        }

    def _generate_actions(self, state):
        if state.terminal:
            return []
        return [
            {"kind": "READ_FILE", "payload": {"path": state.observable.get("symptoms", [""])[0].split(" ")[-1]}, "estimated_cost": 0.001},
            {"kind": "WRITE_FIX", "payload": {"file": state.hidden["file"], "fix": "auto"}, "estimated_cost": 0.005},
            {"kind": "RUN_TESTS", "payload": {}, "estimated_cost": 0.002},
            {"kind": "GIVE_UP", "payload": {}, "estimated_cost": 0.0},
        ]

    def _process_result(self, state, action, result):
        if action.kind == "WRITE_FIX":
            state.correctness = 0.8 if result.status == "ok" else 0.2
            state.completeness = 0.7
        elif action.kind == "RUN_TESTS":
            state.model_calls += 1
        elif action.kind == "GIVE_UP":
            state.correctness = 0.0
            state.terminal = True

    def _detect_failure_modes(self, state):
        modes = super()._detect_failure_modes(state)
        if state.correctness < 0.5:
            modes.append("fix_incorrect")
        if self.genome.information.get("distractors", 0) > 0.3:
            modes.append("distractor_confused")
        return modes


class ResearchVerificationWorld(BaseWorld):
    """Fact-check world: hidden truth claims, observable evidence."""

    def _generate_truth(self, rng):
        n_claims = self.genome.structure.get("n_claims", 5)
        claims = []
        for i in range(n_claims):
            claims.append({
                "id": f"claim_{i}",
                "statement": f"Claim {i} is true",
                "is_true": rng.random() < 0.6,
                "sources": [f"source_{j}" for j in range(rng.randint(1, 4))],
            })
        return {"claims": claims}

    def _generate_observable(self, rng, hidden):
        info = self.genome.information
        conflicting = info.get("conflicting_sources", 0.2)

        evidence = []
        for claim in hidden["claims"]:
            if rng.random() < info.get("observable_fraction", 0.8):
                evidence.append({
                    "claim_id": claim["id"],
                    "supporting": rng.random() > conflicting,
                    "source_reliability": rng.random(),
                })
        return {"evidence": evidence}

    def _generate_actions(self, state):
        if state.terminal:
            return []
        return [
            {"kind": "CHECK_CLAIM", "payload": {"claim_id": f"claim_{i}"}, "estimated_cost": 0.001}
            for i in range(len(state.hidden.get("claims", [])))
        ] + [
            {"kind": "SUBMIT_VERDICT", "payload": {}, "estimated_cost": 0.0},
        ]

    def _process_result(self, state, action, result):
        if action.kind == "CHECK_CLAIM":
            state.model_calls += 1
            state.evidence_quality = min(1.0, state.evidence_quality + 0.1)
        elif action.kind == "SUBMIT_VERDICT":
            state.correctness = state.evidence_quality
            state.terminal = True


class ComputeRoutingWorld(BaseWorld):
    """Compute routing world: model selection under budget constraints."""

    def _generate_truth(self, rng):
        task_difficulty = rng.random()
        return {
            "task_difficulty": task_difficulty,
            "optimal_model": "strong" if task_difficulty > 0.7 else "cheap" if task_difficulty > 0.3 else "free",
            "required_quality": 0.7 + task_difficulty * 0.3,
        }

    def _generate_observable(self, rng, hidden):
        resources = self.genome.resources
        return {
            "task_description": "Complete the following task...",
            "budget_usd": resources.get("budget_usd", 0.10),
            "free_calls_remaining": resources.get("free_calls", 5),
            "cheap_cost": 0.001,
            "strong_cost": 0.01,
            "estimated_difficulty": hidden["task_difficulty"],
        }

    def _generate_actions(self, state):
        if state.terminal:
            return []
        return [
            {"kind": "CALL_FREE", "payload": {"model": "mimo-v2.5"}, "estimated_cost": 0.0},
            {"kind": "CALL_CHEAP", "payload": {"model": "llama-3.3-70b"}, "estimated_cost": 0.001},
            {"kind": "CALL_STRONG", "payload": {"model": "gpt-4o"}, "estimated_cost": 0.01},
            {"kind": "SUBMIT", "payload": {}, "estimated_cost": 0.0},
        ]

    def _process_result(self, state, action, result):
        if action.kind.startswith("CALL_"):
            state.model_calls += 1
            cost = result.cash_cost
            state.total_cost_usd += cost
            # Quality depends on model choice vs task difficulty
            model_power = {"CALL_FREE": 0.5, "CALL_CHEAP": 0.7, "CALL_STRONG": 0.9}
            power = model_power.get(action.kind, 0.5)
            difficulty = state.hidden.get("task_difficulty", 0.5)
            state.correctness = min(1.0, power * (1.0 + difficulty * 0.3))
        elif action.kind == "SUBMIT":
            state.terminal = True


# ─── Registry ─────────────────────────────────────────────────────────

_WORLD_CLASSES: dict[str, type[BaseWorld]] = {
    "software.implementation": SoftwareBugFixWorld,
    "software.maintenance": SoftwareBugFixWorld,
    "research.verification": ResearchVerificationWorld,
    "research.analysis": ResearchVerificationWorld,
    "compute.routing": ComputeRoutingWorld,
}


def compile_world(genome: WorldGenome) -> BaseWorld:
    """Compile a WorldGenome into an executable CG world."""
    cls = _WORLD_CLASSES.get(genome.family_id, BaseWorld)
    return cls(genome)


def register_world_class(family_id: str, cls: type[BaseWorld]):
    """Register a world class for a family."""
    _WORLD_CLASSES[family_id] = cls
