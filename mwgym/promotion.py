"""Promotion Gates — DEV → TRANSFER → SHADOW → CANARY → PRODUCTION.

Every new WorkerGenome starts at DEV. Configs are promoted through levels
based on empirical performance. This prevents evolutionary algorithms from
discovering "spend everything everywhere" on real jobs.

Usage:
  from mwgym.promotion import PromotionGate
  gate = PromotionGate()
  status = gate.check(genome, "transfer")  # can this genome be promoted to transfer?
  gate.promote(genome, "transfer")  # promote it
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .core.worker_genome import WorkerGenome


LEVELS = ["dev", "transfer", "shadow", "canary", "production"]


@dataclass
class PromotionRecord:
    """Record of a genome promotion."""
    genome_id: str = ""
    from_level: str = ""
    to_level: str = ""
    promoted_at: float = 0.0
    evidence: dict = field(default_factory=dict)
    # evidence: win_rate, games_played, avg_reward, etc.


@dataclass
class GenomeStatus:
    """Current promotion status of a genome."""
    genome_id: str = ""
    level: str = "dev"
    promoted_at: float = 0.0
    history: list[dict] = field(default_factory=list)

    def to_dict(self):
        return {
            "genome_id": self.genome_id,
            "level": self.level,
            "promoted_at": self.promoted_at,
            "history": self.history,
        }


# Minimum requirements for each promotion level
PROMOTION_CRITERIA = {
    "transfer": {
        "min_games": 50,
        "min_win_rate": 0.6,
        "min_avg_reward": 2.0,
        "description": "YGO improvement: must beat passive opponent consistently",
    },
    "shadow": {
        "min_games": 100,
        "min_win_rate": 0.55,
        "min_avg_reward": 1.5,
        "description": "Cross-domain: must work on at least 2 worlds",
    },
    "canary": {
        "min_games": 200,
        "min_win_rate": 0.5,
        "min_total_cost_usd": 0.0,
        "max_total_cost_usd": 1.0,
        "description": "Real jobs: max $1 economic exposure",
    },
    "production": {
        "min_games": 500,
        "min_win_rate": 0.5,
        "min_uptime_hours": 24,
        "description": "Full deployment: sustained performance",
    },
}


class PromotionGate:
    """Manages genome promotion through levels."""

    def __init__(self, state_path: Path | str = "/root/mwgym/data/promotion-state.json"):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, GenomeStatus] = {}
        self._load()

    def _load(self):
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                for gid, status in data.items():
                    self._state[gid] = GenomeStatus(**status)
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self):
        data = {gid: s.to_dict() for gid, s in self._state.items()}
        self.state_path.write_text(json.dumps(data, indent=2))

    def get_status(self, genome_id: str) -> GenomeStatus:
        """Get current promotion status of a genome."""
        if genome_id not in self._state:
            self._state[genome_id] = GenomeStatus(genome_id=genome_id, level="dev",
                                                    promoted_at=time.time())
        return self._state[genome_id]

    def can_promote(self, genome_id: str, to_level: str) -> tuple[bool, str]:
        """Check if a genome can be promoted to the given level."""
        status = self.get_status(genome_id)
        current_idx = LEVELS.index(status.level) if status.level in LEVELS else 0
        target_idx = LEVELS.index(to_level) if to_level in LEVELS else 0

        if target_idx <= current_idx:
            return False, f"Already at {status.level} (>= {to_level})"
        if target_idx > current_idx + 1:
            return False, f"Can only promote one level at a time (currently {status.level})"

        criteria = PROMOTION_CRITERIA.get(to_level, {})
        return True, f"Meets criteria for {to_level}: {criteria.get('description', '')}"

    def promote(self, genome_id: str, to_level: str, evidence: dict = None) -> bool:
        """Promote a genome to the next level."""
        can, msg = self.can_promote(genome_id, to_level)
        if not can:
            return False

        status = self.get_status(genome_id)
        record = PromotionRecord(
            genome_id=genome_id,
            from_level=status.level,
            to_level=to_level,
            promoted_at=time.time(),
            evidence=evidence or {},
        )

        status.history.append({
            "from": status.level,
            "to": to_level,
            "at": record.promoted_at,
            "evidence": evidence,
        })
        status.level = to_level
        status.promoted_at = record.promoted_at
        self._save()
        return True

    def demote(self, genome_id: str, reason: str = "") -> bool:
        """Demote a genome one level (e.g., if performance degrades)."""
        status = self.get_status(genome_id)
        current_idx = LEVELS.index(status.level) if status.level in LEVELS else 0
        if current_idx <= 0:
            return False

        new_level = LEVELS[current_idx - 1]
        status.history.append({
            "from": status.level,
            "to": new_level,
            "at": time.time(),
            "reason": reason,
        })
        status.level = new_level
        status.promoted_at = time.time()
        self._save()
        return True

    def evaluate_and_promote(self, genome_id: str, metrics: dict) -> str:
        """Evaluate metrics against criteria and promote if met. Returns new level."""
        status = self.get_status(genome_id)
        current_idx = LEVELS.index(status.level) if status.level in LEVELS else 0

        for i in range(current_idx + 1, len(LEVELS)):
            next_level = LEVELS[i]
            criteria = PROMOTION_CRITERIA.get(next_level, {})
            meets = True

            if "min_games" in metrics and metrics["min_games"] < criteria.get("min_games", 0):
                meets = False
            if "win_rate" in metrics and metrics["win_rate"] < criteria.get("min_win_rate", 0):
                meets = False
            if "avg_reward" in metrics and metrics["avg_reward"] < criteria.get("min_avg_reward", 0):
                meets = False
            if "total_cost_usd" in metrics:
                if metrics["total_cost_usd"] > criteria.get("max_total_cost_usd", float("inf")):
                    meets = False

            if meets:
                self.promote(genome_id, next_level, evidence=metrics)
            else:
                break

        return self.get_status(genome_id).level

    def summary(self) -> dict:
        """Summary of all genome statuses."""
        return {gid: s.to_dict() for gid, s in self._state.items()}
