"""Curriculum — selects next worlds for worker training.

Uses the MAP-Elites archive from the Adversary to choose worlds that:
1. Target the worker's weakest capabilities
2. Are at the training frontier (not too easy, not impossible)
3. Haven't been over-replayed
4. Cover the niche space evenly
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from ..schema.world import WorldGenome
from .adversary import Adversary


@dataclass
class CurriculumConfig:
    """Configuration for curriculum selection."""
    # How many worlds to select per batch
    batch_size: int = 5

    # Replay vs novelty ratio
    replay_ratio: float = 0.6    # 60% replay best, 40% explore niches

    # Difficulty bounds
    min_difficulty: int = 1
    max_difficulty: int = 10

    # Success rate bounds (training frontier)
    target_success_low: float = 0.3
    target_success_high: float = 0.75

    # Anti-collapse: max replays per niche
    max_replays_per_niche: int = 3

    # Random seed
    seed: int = 42


class Curriculum:
    """Selects worlds from the adversary's archive based on worker weakness."""

    def __init__(self, adversary: Adversary, config: CurriculumConfig | None = None):
        self.adversary = adversary
        self.config = config or CurriculumConfig()
        self.rng = random.Random(self.config.seed)
        self.replay_counts: dict[str, int] = {}  # niche → count

    def select_next(self, worker_caps: dict[str, float] | None = None,
                     recent_runs: list[dict] | None = None) -> list[dict]:
        """Select the next batch of worlds to present to the worker.

        Args:
            worker_caps: {capability_name: score} from recent runs
            recent_runs: recent FailureVectors for this worker

        Returns:
            List of {"world_id": ..., "niche": ..., "priority": ..., "reason": ...}
        """
        archive = self.adversary.archive
        if not archive:
            return []

        # Score each world for this worker
        scored = []
        for entry in archive:
            score = self._score_for_worker(entry, worker_caps, recent_runs)
            scored.append((score, entry))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Split into replay and exploration
        n_replay = int(self.config.batch_size * self.config.replay_ratio)
        n_explore = self.config.batch_size - n_replay

        selections = []

        # Replay: best scored worlds that haven't been over-replayed
        for score, entry in scored:
            if len(selections) >= n_replay:
                break
            niche = entry["niche"]
            if self.replay_counts.get(niche, 0) >= self.config.max_replays_per_niche:
                continue
            selections.append({
                "world_id": entry["world_id"],
                "niche": niche,
                "priority": score,
                "reason": "replay_weakness",
                "difficulty": entry.get("difficulty", 5),
            })
            self.replay_counts[niche] = self.replay_counts.get(niche, 0) + 1

        # Exploration: underserved niches
        niche_counts = {}
        for entry in archive:
            niche = entry["niche"]
            niche_counts[niche] = niche_counts.get(niche, 0) + 1

        # Find niches with few replays
        underserved = []
        for entry in archive:
            niche = entry["niche"]
            if self.replay_counts.get(niche, 0) == 0:
                underserved.append(entry)

        self.rng.shuffle(underserved)
        for entry in underserved:
            if len(selections) >= self.config.batch_size:
                break
            selections.append({
                "world_id": entry["world_id"],
                "niche": entry["niche"],
                "priority": 0.5,
                "reason": "explore_niche",
                "difficulty": entry.get("difficulty", 5),
            })

        # Fill remaining with random from archive
        if len(selections) < self.config.batch_size:
            remaining = [e for e in archive
                        if e["world_id"] not in {s["world_id"] for s in selections}]
            self.rng.shuffle(remaining)
            for entry in remaining[:self.config.batch_size - len(selections)]:
                selections.append({
                    "world_id": entry["world_id"],
                    "niche": entry["niche"],
                    "priority": 0.3,
                    "reason": "fill",
                    "difficulty": entry.get("difficulty", 5),
                })

        return selections[:self.config.batch_size]

    def _score_for_worker(self, entry: dict,
                           worker_caps: dict[str, float] | None,
                           recent_runs: list[dict] | None) -> float:
        """Score how useful a world is for this specific worker."""
        score = 0.5  # base

        # Frontier bonus: success rate near 50%
        success_rate = entry.get("worker_success_rate", 0.5)
        frontier = 1.0 - abs(success_rate - 0.5) * 2
        score += frontier * 0.3

        # Weakness targeting: if worker is weak on this niche's failure mode
        if worker_caps:
            niche_parts = entry.get("niche", "").split("×")
            if niche_parts:
                failure_mode = niche_parts[0]
                # Check if worker has failed on this recently
                if recent_runs:
                    recent_failures = set()
                    for run in recent_runs:
                        fv = run.get("failure_vector", {})
                        for fm in fv.get("failure_modes", []):
                            recent_failures.add(fm)
                    if failure_mode in recent_failures:
                        score += 0.3

        # Difficulty targeting: prefer worlds near the worker's level
        difficulty = entry.get("difficulty", 5)
        if self.config.min_difficulty <= difficulty <= self.config.max_difficulty:
            score += 0.1

        return min(1.0, score)

    def record_replay(self, world_id: str, niche: str):
        """Record that a world was replayed."""
        self.replay_counts[niche] = self.replay_counts.get(niche, 0) + 1

    def stats(self) -> dict:
        """Get curriculum statistics."""
        return {
            "archive_size": len(self.adversary.archive),
            "niche_counts": dict(self.replay_counts),
            "total_replays": sum(self.replay_counts.values()),
            "mutation_counts": dict(self.adversary.mutation_counts),
            "generation": self.adversary.generation,
        }
