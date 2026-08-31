"""YGO Evaluator — deterministic scoring."""
from __future__ import annotations


def evaluate_game(game_history: list[dict], final_state: dict) -> dict:
    """Score a completed game."""
    total_reward = sum(h.get("reward", 0) for h in game_history)
    won = final_state.get("opponent_hp", 0) <= 0
    turns = final_state.get("turn", 1)

    # Efficiency: reward per turn
    efficiency = total_reward / max(1, turns)

    # Budget efficiency: credits used well
    credits_used = sum(h.get("action", {}).get("cost", 0) for h in game_history)
    credit_efficiency = total_reward / max(1, credits_used)

    # Decision quality: how many good decisions
    good_decisions = sum(1 for h in game_history if h.get("reward", 0) > 0)
    total_decisions = len(game_history)
    decision_quality = good_decisions / max(1, total_decisions)

    return {
        "won": won,
        "total_reward": round(total_reward, 3),
        "turns": turns,
        "efficiency": round(efficiency, 3),
        "credit_efficiency": round(credit_efficiency, 3),
        "decision_quality": round(decision_quality, 3),
        "player_hp": final_state.get("player_hp", 0),
        "opponent_hp": final_state.get("opponent_hp", 0),
    }
