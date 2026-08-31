"""DecisionFeatureExtractor — extracts generic features from game state.

Per spec Section 29: use domain-independent features wherever possible.

Core features:
- branching factor
- policy entropy
- top1/top2 margin
- estimated uncertainty
- estimated irreversibility
- stakes
- remaining-budget fraction
- verification strength
- memory-match quality
- previous failure rate
- distance-to-terminal estimate
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class DecisionFeatures:
    """Generic features for a decision point."""
    branching_factor: int = 0
    policy_entropy: float = 0.0
    top1_top2_margin: float = 0.0
    estimated_uncertainty: float = 0.0
    estimated_irreversibility: float = 0.0
    stakes: float = 0.0
    remaining_budget_fraction: float = 1.0
    verification_strength: float = 0.0
    memory_match_score: float = 0.0
    previous_failure_rate: float = 0.0
    distance_to_terminal_estimate: float = 0.5

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class DecisionFeatureExtractor:
    """Extracts generic features from YGO game state."""

    def __init__(self, total_budget: float = 1000.0):
        self.total_budget = total_budget
        self.games_played = 0
        self.games_won = 0

    def extract(self, obs, available_actions: list[dict],
                budget_remaining: float = 0.0,
                memory_match_score: float = 0.0) -> DecisionFeatures:
        """Extract features from current state."""
        # Branching factor
        branching_factor = len(available_actions)

        # Policy entropy (uniform distribution over legal actions)
        if branching_factor > 0:
            policy_entropy = math.log(branching_factor)
        else:
            policy_entropy = 0.0

        # Top1/top2 margin (estimate from action values)
        values = [a.get("estimated_value", 0) for a in available_actions]
        if len(values) >= 2:
            sorted_values = sorted(values, reverse=True)
            top1_top2_margin = sorted_values[0] - sorted_values[1]
        elif len(values) == 1:
            top1_top2_margin = values[0]
        else:
            top1_top2_margin = 0.0

        # Estimated uncertainty (based on hp ratio and opponent field)
        player_hp = obs[0] if len(obs) > 0 else 4000
        opponent_hp = obs[1] if len(obs) > 0 else 4000
        hp_ratio = player_hp / max(1, opponent_hp + player_hp)
        estimated_uncertainty = abs(0.5 - hp_ratio) * 2  # 0 when balanced, 1 when extreme

        # Estimated irreversibility (attack actions are more irreversible)
        attack_actions = [a for a in available_actions if a.get("type") == "attack"]
        estimated_irreversibility = len(attack_actions) / max(1, branching_factor)

        # Stakes (based on hp difference)
        hp_diff = abs(player_hp - opponent_hp)
        stakes = hp_diff / 8000  # normalized to [0, 1]

        # Remaining budget fraction
        remaining_budget_fraction = budget_remaining / max(1, self.total_budget)

        # Verification strength (low for YGO, high for coding)
        verification_strength = 0.3  # YGO has some verification via rollout

        # Memory match score (from external memory)
        memory_match_score = memory_match_score

        # Previous failure rate
        if self.games_played > 0:
            previous_failure_rate = 1.0 - (self.games_won / self.games_played)
        else:
            previous_failure_rate = 0.0

        # Distance to terminal estimate (based on hp and turn)
        turn = obs[5] if len(obs) > 5 else 1
        distance_to_terminal_estimate = max(0, 1.0 - turn / 20)

        return DecisionFeatures(
            branching_factor=branching_factor,
            policy_entropy=policy_entropy,
            top1_top2_margin=top1_top2_margin,
            estimated_uncertainty=estimated_uncertainty,
            estimated_irreversibility=estimated_irreversibility,
            stakes=stakes,
            remaining_budget_fraction=remaining_budget_fraction,
            verification_strength=verification_strength,
            memory_match_score=memory_match_score,
            previous_failure_rate=previous_failure_rate,
            distance_to_terminal_estimate=distance_to_terminal_estimate,
        )

    def record_outcome(self, won: bool):
        """Record game outcome for failure rate tracking."""
        self.games_played += 1
        if won:
            self.games_won += 1
