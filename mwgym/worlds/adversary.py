"""Adversary — failure-guided WorldGenome mutation.

Reads FailureVectors to decide how to mutate the next WorldGenome.
The adversary's goal is NOT to make the worker fail maximally.
It's to create worlds at the worker's training frontier:
  - near misses (worker almost succeeded)
  - specific capability weaknesses
  - economically important failures
  - combinations that expose correlated weaknesses

Uses the CGE peer-reviewed feedback machinery adapted for world evolution.

Wired to CG evolution recipes for mutation strategies.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..schema.world import FailureVector, WorldGenome

# Add CG to path for evolution recipes
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "cg"))


# ─── Mutation Strategies ──────────────────────────────────────────────

@dataclass
class MutationStrategy:
    """A strategy for mutating a WorldGenome based on failure patterns."""
    name: str = ""
    target_failure_modes: tuple[str, ...] = ()
    target_weak_capabilities: tuple[str, ...] = ()
    description: str = ""

    def applies_to(self, fv: FailureVector) -> bool:
        """Check if this strategy applies to the given failure vector."""
        if self.target_failure_modes:
            if any(fm in fv.failure_modes for fm in self.target_failure_modes):
                return True
        if self.target_weak_capabilities:
            weak = fv.weakest_capabilities(top_k=3)
            if any(cap in self.target_weak_capabilities for cap in weak):
                return True
        return False


# Canonical mutation strategies
STRATEGIES = {
    "staleness_increase": MutationStrategy(
        name="staleness_increase",
        target_failure_modes=("stale_source_selected", "incorrect_answer"),
        target_weak_capabilities=("source.verify", "source.freshness"),
        description="Increase stale evidence proportion",
    ),
    "conflict_injection": MutationStrategy(
        name="conflict_injection",
        target_failure_modes=("contradiction_ignored", "evidence_conflict"),
        target_weak_capabilities=("source.independently", "claim.support"),
        description="Add contradicting sources with similar authority",
    ),
    "distractor_growth": MutationStrategy(
        name="distractor_growth",
        target_failure_modes=("distractor_confused", "irrelevant_info"),
        target_weak_capabilities=("source.verify", "claim.correct"),
        description="Increase irrelevant but plausible information",
    ),
    "budget_squeeze": MutationStrategy(
        name="budget_squeeze",
        target_failure_modes=("budget_exceeded", "unnecessary_paid_call"),
        target_weak_capabilities=("budget.manage", "model.select"),
        description="Reduce available budget or increase task difficulty",
    ),
    "step_pressure": MutationStrategy(
        name="step_pressure",
        target_failure_modes=("step_limit_reached", "incomplete"),
        target_weak_capabilities=("process.verify", "code.write"),
        description="Reduce max steps to force faster completion",
    ),
    "debug_challenge": MutationStrategy(
        name="debug_challenge",
        target_failure_modes=("fix_incorrect", "regression"),
        target_weak_capabilities=("code.debug", "regression.detect"),
        description="Introduce subtler bugs with misleading symptoms",
    ),
    "execution_hardening": MutationStrategy(
        name="execution_hardening",
        target_failure_modes=("execution_failed", "no_artifacts", "model_error"),
        target_weak_capabilities=("code.write", "reasoning.default"),
        description="Make task requirements stricter to force correct execution",
    ),
    "novelty_injection": MutationStrategy(
        name="novelty_injection",
        target_failure_modes=(),  # always applicable as fallback
        target_weak_capabilities=(),
        description="Random perturbation to prevent curriculum collapse",
    ),
}


# ─── MAP-Elites Niches ────────────────────────────────────────────────

def _niche_key(fv: FailureVector, world: WorldGenome) -> str:
    """Generate a MAP-Elites niche key from failure vector and world."""
    # Primary dimensions: dominant failure type × difficulty
    primary_failures = list(fv.failure_modes)[:2] if fv.failure_modes else ["none"]
    difficulty_bin = "easy" if world.difficulty <= 3 else "medium" if world.difficulty <= 6 else "hard"
    cost_bin = "cheap" if world.resources.get("budget_usd", 0.1) < 0.05 else "expensive"

    return f"{primary_failures[0]}×{difficulty_bin}×{cost_bin}"


# ─── Adversary ────────────────────────────────────────────────────────

class Adversary:
    """Failure-guided WorldGenome mutator.

    Reads FailureVectors from completed runs, selects mutation strategies,
    and produces child WorldGenomes that target the worker's weaknesses.
    """

    def __init__(self, family_id: str, rng_seed: int = 42):
        self.family_id = family_id
        self.rng = random.Random(rng_seed)
        self.generation = 0
        self.archive: list[dict] = []  # MAP-Elites archive entries
        self.mutation_counts: dict[str, int] = {}

    def select_strategy(self, fv: FailureVector) -> MutationStrategy:
        """Select the best mutation strategy for this failure vector."""
        applicable = [s for s in STRATEGIES.values() if s.applies_to(fv)]

        if not applicable:
            return STRATEGIES["novelty_injection"]

        # Weight by how badly the worker failed on this strategy's targets
        weights = []
        for s in applicable:
            mode_hits = sum(1 for fm in fv.failure_modes if fm in s.target_failure_modes)
            cap_hits = sum(1 for c in fv.capabilities
                          if c.capability in s.target_weak_capabilities and c.score < 0.5)
            weight = 1.0 + mode_hits * 2.0 + cap_hits * 1.5
            weights.append(weight)

        # Select proportionally to weight
        total = sum(weights)
        if total == 0:
            return self.rng.choice(applicable)

        r = self.rng.random() * total
        cumulative = 0
        for s, w in zip(applicable, weights):
            cumulative += w
            if r <= cumulative:
                return s

        return applicable[-1]

    def mutate(self, parent: WorldGenome, fv: FailureVector) -> WorldGenome:
        """Create a child WorldGenome from parent + failure vector.
        
        Uses CG evolution recipes when available, falls back to local mutation.
        """
        # Try CG evolution recipes first
        child = self._try_cg_evolution(parent, fv)
        if child:
            self.generation += 1
            niche = _niche_key(fv, child)
            return child, "cg_evolution", niche
        
        # Fall back to local mutation strategies
        strategy = self.select_strategy(fv)
        self.generation += 1
        self.mutation_counts[strategy.name] = self.mutation_counts.get(strategy.name, 0) + 1

        # Apply mutation
        child = self._apply_mutation(parent, strategy, fv)

        # Compute niche for MAP-Elites
        niche = _niche_key(fv, child)

        return child, strategy.name, niche
    
    def _try_cg_evolution(self, parent: WorldGenome, fv: FailureVector) -> WorldGenome | None:
        """Try to use CG evolution recipes for mutation.
        
        Returns None if CG is not available or fails.
        """
        try:
            from cogym_kernel.evo.recipes import EvolutionContext, propose_children
            
            # Create evolution context from current state
            ctx = EvolutionContext(
                elite_configs=[parent.to_dict()],
                scorecard=[{
                    "config": parent.to_dict(),
                    "metrics": {
                        "quality": 1.0 - fv.failure_severity,
                        "cost": fv.regret_usd,
                    },
                }],
                hydra_leaders=[],
                search_space={
                    "difficulty": (1, 10),
                    "budget_usd": (0.005, 0.1),
                },
                rng=self.rng,
            )
            
            # Use CG's mutation recipe
            children = propose_children("failure_guided", ctx, n_children=1)
            if children:
                child_dict = children[0]
                # Convert back to WorldGenome
                return WorldGenome(
                    id=child_dict.get("id", f"cg-{self.generation}"),
                    parent_id=parent.id,
                    generation=self.generation,
                    family_id=parent.family_id,
                    difficulty=child_dict.get("difficulty", parent.difficulty),
                    seed=self.rng.randint(0, 2**31),
                    structure=child_dict.get("structure", parent.structure),
                    information=child_dict.get("information", parent.information),
                    resources=child_dict.get("resources", parent.resources),
                )
        except Exception:
            pass
        
        return None

    def _apply_mutation(self, parent: WorldGenome, strategy: MutationStrategy,
                         fv: FailureVector) -> WorldGenome:
        """Apply a specific mutation strategy to produce a child."""
        # Start from parent
        structure = dict(parent.structure)
        information = dict(parent.information)
        resources = dict(parent.resources)
        perturbations = dict(parent.perturbations)

        # Apply strategy-specific mutations
        if strategy.name == "staleness_increase":
            information["stale_sources"] = min(0.8, information.get("stale_sources", 0.1) + 0.15)
            information["observable_fraction"] = max(0.3, information.get("observable_fraction", 0.6) - 0.1)

        elif strategy.name == "conflict_injection":
            information["conflicting_sources"] = min(0.7, information.get("conflicting_sources", 0.1) + 0.2)
            perturbations["source_laundering"] = True

        elif strategy.name == "distractor_growth":
            information["distractors"] = min(0.8, information.get("distractors", 0.2) + 0.15)
            structure["n_irrelevant_files"] = structure.get("n_irrelevant_files", 2) + 3

        elif strategy.name == "budget_squeeze":
            resources["budget_usd"] = max(0.005, resources.get("budget_usd", 0.1) * 0.7)
            resources["free_calls"] = max(1, resources.get("free_calls", 5) - 2)

        elif strategy.name == "step_pressure":
            structure["max_steps"] = max(3, structure.get("max_steps", 10) - 2)

        elif strategy.name == "debug_challenge":
            structure["bug_subtlety"] = min(1.0, structure.get("bug_subtlety", 0.3) + 0.2)
            perturbations["misleading_symptoms"] = True
            perturbations["regression_landmine"] = True

        elif strategy.name == "execution_hardening":
            # Tighten requirements to force correct execution
            resources["budget_usd"] = max(0.005, resources.get("budget_usd", 0.1) * 0.8)
            structure["strict_output"] = True
            structure["require_all_fields"] = True
            perturbations["output_validation"] = True

        elif strategy.name == "novelty_injection":
            # Random perturbation
            key = self.rng.choice(["stale_sources", "conflicting_sources", "distractors",
                                   "budget_usd", "max_steps"])
            if key in information:
                information[key] = min(0.8, information.get(key, 0.1) + self.rng.uniform(-0.1, 0.2))
            elif key in resources:
                resources[key] = max(0.005, resources.get(key, 0.1) * self.rng.uniform(0.7, 1.3))
            elif key in structure:
                structure[key] = max(2, structure.get(key, 5) + self.rng.randint(-2, 3))

        # Increase difficulty
        difficulty = min(10, parent.difficulty + 1)

        # New seed
        seed = int.from_bytes(hashlib.sha256(
            f"{parent.seed}:{self.generation}:{strategy.name}".encode()
        ).digest()[:4], "big")

        child_id = hashlib.sha256(
            json.dumps({"parent": parent.id, "gen": self.generation,
                        "strategy": strategy.name, "seed": seed},
                       sort_keys=True).encode()
        ).hexdigest()[:16]

        return WorldGenome(
            id=child_id,
            parent_id=parent.id,
            generation=self.generation,
            family_id=parent.family_id,
            difficulty=difficulty,
            seed=seed,
            structure=structure,
            information=information,
            resources=resources,
            dynamics=parent.dynamics,
            perturbations=perturbations,
            evaluator=parent.evaluator,
            parent_ids=(parent.id,),
            created_at=time.time(),
        )

    def objective(self, fv: FailureVector, world: WorldGenome) -> float:
        """Teacher objective for world quality.

        A good world:
        - has high learning_progress (worker improved vs baseline)
        - has high student_regret (worker failed but almost succeeded)
        - is at the training frontier (success rate 35-75%)
        - is realistic (not impossible)
        """
        # Frontier score: best at 50% success rate
        success_rate = 1.0 - fv.failure_severity
        frontier = 1.0 - abs(success_rate - 0.5) * 2  # peaks at 0.5

        # Regret: how close was the worker to succeeding?
        regret = 1.0 - fv.failure_severity if fv.failure_severity < 0.5 else 0.3

        # Realism: penalize impossible worlds
        realism = 1.0 if fv.gates_passed > 0 else 0.2

        # Novelty: penalize overused mutations
        niche = _niche_key(fv, world)
        niche_count = sum(1 for e in self.archive if e.get("niche") == niche)
        novelty = max(0.1, 1.0 - niche_count * 0.15)

        return frontier * 0.3 + regret * 0.3 + realism * 0.2 + novelty * 0.2

    def archive_world(self, world: WorldGenome, fv: FailureVector, score: float):
        """Add a world to the MAP-Elites archive."""
        niche = _niche_key(fv, world)
        entry = {
            "world_id": world.id,
            "niche": niche,
            "score": score,
            "difficulty": world.difficulty,
            "worker_success_rate": 1.0 - fv.failure_severity,
            "created_at": time.time(),
        }

        # Replace if better
        for i, existing in enumerate(self.archive):
            if existing["niche"] == niche:
                if score > existing["score"]:
                    self.archive[i] = entry
                return

        self.archive.append(entry)

    def get_curriculum(self, top_k: int = 10) -> list[dict]:
        """Get the best worlds from the archive for replay."""
        sorted_archive = sorted(self.archive, key=lambda e: e["score"], reverse=True)
        return sorted_archive[:top_k]

    def save_archive(self, hydra) -> int:
        """Persist archive to Hydra's curriculum_archive table. Returns count saved."""
        saved = 0
        for entry in self.archive:
            hydra.record_curriculum(
                family_id=self.family_id,
                niche_key=entry.get("niche", ""),
                world_genome_id=entry.get("world_id", ""),
                difficulty=entry.get("difficulty", 5),
                discriminative_power=entry.get("score", 0.0),
                worker_success_rate=entry.get("worker_success_rate", 0.5),
            )
            saved += 1
        return saved

    def load_archive(self, hydra) -> int:
        """Load archive from Hydra. Returns count loaded."""
        entries = hydra.get_curriculum(family_id=self.family_id)
        self.archive = []
        for e in entries:
            self.archive.append({
                "world_id": e.get("world_genome_id", ""),
                "niche": e.get("niche_key", ""),
                "score": e.get("discriminative_power", 0.0),
                "difficulty": e.get("difficulty", 5),
                "worker_success_rate": e.get("worker_success_rate", 0.5),
                "created_at": e.get("created_at", 0.0),
            })
        return len(self.archive)
