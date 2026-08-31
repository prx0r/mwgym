"""MetaActionExecutor — executes allocator decisions as resource-augmented actions.

Per spec Section 22: canonical allocator action space.

MetaActions:
- ACT_NOW: act immediately with base policy
- RETRIEVE: get experience from Hydra
- ROLLOUT_4: simulate 4 candidate actions
- ROLLOUT_16: simulate 16 candidate actions
- LETTA_REASON: use Letta for reasoning
- CHEAP_MODEL: use cheap model
- STRONG_MODEL: use strong model
- VERIFY: verify action/value estimate
- SUMMARIZE: compress current strategic state
- PIVOT: examine alternative action
- STOP_SEARCH: stop searching and act
"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass


class MetaAction(Enum):
    ACT_NOW = "act_now"
    RETRIEVE = "retrieve"
    ROLLOUT_4 = "rollout_4"
    ROLLOUT_16 = "rollout_16"
    LETTA_REASON = "letta_reason"
    CHEAP_MODEL = "cheap_model"
    STRONG_MODEL = "strong_model"
    VERIFY = "verify"
    SUMMARIZE = "summarize"
    PIVOT = "pivot"
    STOP_SEARCH = "stop_search"


@dataclass
class ResourceSpend:
    """Resources spent by a meta-action."""
    credits: int = 0
    model_calls: int = 0
    tokens: int = 0


# Cost table for meta-actions (in credits)
META_ACTION_COSTS = {
    MetaAction.ACT_NOW: ResourceSpend(credits=0),
    MetaAction.RETRIEVE: ResourceSpend(credits=2, tokens=500),
    MetaAction.ROLLOUT_4: ResourceSpend(credits=8, model_calls=4, tokens=2000),
    MetaAction.ROLLOUT_16: ResourceSpend(credits=24, model_calls=16, tokens=8000),
    MetaAction.LETTA_REASON: ResourceSpend(credits=15, model_calls=1, tokens=1500),
    MetaAction.CHEAP_MODEL: ResourceSpend(credits=8, model_calls=1, tokens=1000),
    MetaAction.STRONG_MODEL: ResourceSpend(credits=30, model_calls=1, tokens=3000),
    MetaAction.VERIFY: ResourceSpend(credits=40, model_calls=2, tokens=4000),
    MetaAction.SUMMARIZE: ResourceSpend(credits=4, model_calls=1, tokens=500),
    MetaAction.PIVOT: ResourceSpend(credits=0),
    MetaAction.STOP_SEARCH: ResourceSpend(credits=0),
}


class MetaActionExecutor:
    """Executes meta-actions as resource-augmented decisions.

    For YGO-001, most meta-actions are simulated (not real LLM calls).
    The key is that the DECISION to use a meta-action is real.
    """

    def __init__(self, total_budget: int = 1000):
        self.total_budget = total_budget
        self.remaining_budget = total_budget
        self.spent_history: list[dict] = []

    def can_afford(self, action: MetaAction) -> bool:
        """Check if we can afford a meta-action."""
        cost = META_ACTION_COSTS.get(action, ResourceSpend())
        return self.remaining_budget >= cost.credits

    def execute(self, action: MetaAction, base_action: int = 0,
                available_actions: list[dict] = None) -> dict:
        """Execute a meta-action, return resource spend and modified action."""
        cost = META_ACTION_COSTS.get(action, ResourceSpend())

        if not self.can_afford(action):
            return {
                "action": MetaAction.ACT_NOW,
                "spend": META_ACTION_COSTS[MetaAction.ACT_NOW],
                "result": "insufficient_budget",
                "modified_action": base_action,
            }

        # Deduct budget
        self.remaining_budget -= cost.credits
        self.spent_history.append({
            "action": action.value,
            "cost_credits": cost.credits,
            "remaining": self.remaining_budget,
        })

        # Execute based on action type
        if action == MetaAction.ACT_NOW:
            return {
                "action": action,
                "spend": cost,
                "result": "acted",
                "modified_action": base_action,
            }

        elif action == MetaAction.ROLLOUT_4:
            # Simulate 4 rollouts (in real implementation, this would be tree search)
            return {
                "action": action,
                "spend": cost,
                "result": "simulated_4_rollouts",
                "modified_action": base_action,
            }

        elif action == MetaAction.ROLLOUT_16:
            return {
                "action": action,
                "spend": cost,
                "result": "simulated_16_rollouts",
                "modified_action": base_action,
            }

        elif action == MetaAction.RETRIEVE:
            return {
                "action": action,
                "spend": cost,
                "result": "retrieved_experience",
                "modified_action": base_action,
            }

        elif action == MetaAction.LETTA_REASON:
            return {
                "action": action,
                "spend": cost,
                "result": "letta_reasoning_complete",
                "modified_action": base_action,
            }

        elif action == MetaAction.CHEAP_MODEL:
            return {
                "action": action,
                "spend": cost,
                "result": "cheap_model_consulted",
                "modified_action": base_action,
            }

        elif action == MetaAction.STRONG_MODEL:
            return {
                "action": action,
                "spend": cost,
                "result": "strong_model_consulted",
                "modified_action": base_action,
            }

        elif action == MetaAction.VERIFY:
            return {
                "action": action,
                "spend": cost,
                "result": "verification_complete",
                "modified_action": base_action,
            }

        elif action == MetaAction.SUMMARIZE:
            return {
                "action": action,
                "spend": cost,
                "result": "state_summarized",
                "modified_action": base_action,
            }

        elif action == MetaAction.PIVOT:
            # Pivot: try a different action
            if available_actions and len(available_actions) > 1:
                # Pick second-best action
                new_action = 1 if base_action == 0 else 0
                return {
                    "action": action,
                    "spend": cost,
                    "result": "pivoted_to_alternative",
                    "modified_action": new_action,
                }
            return {
                "action": action,
                "spend": cost,
                "result": "no_alternative_available",
                "modified_action": base_action,
            }

        elif action == MetaAction.STOP_SEARCH:
            return {
                "action": action,
                "spend": cost,
                "result": "search_stopped",
                "modified_action": base_action,
            }

        return {
            "action": action,
            "spend": cost,
            "result": "unknown_action",
            "modified_action": base_action,
        }

    def budget_report(self) -> dict:
        """Report on budget usage."""
        total_spent = self.total_budget - self.remaining_budget
        return {
            "total_budget": self.total_budget,
            "remaining": self.remaining_budget,
            "spent": total_spent,
            "utilization": total_spent / max(1, self.total_budget),
            "actions_taken": len(self.spent_history),
        }
