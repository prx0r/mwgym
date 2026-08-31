"""YGO World — deterministic Yu-Gi-Oh environment for testing resource allocation.

Closed world, perfect information, synthetic economics.
Tests L0 (reasoning) and L1 (execution) allocation.

Turn structure:
  Each side gets ACTION_BUDGET actions per turn (play, buy, attack).
  Then end_turn triggers the other side's turn.
  This ensures both sides have equal capability.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

ACTION_BUDGET = 3  # actions per turn per side

CARDS = [
    {"id": "c1", "name": "Dragon Lord", "attack": 2800, "defense": 2200, "cost": 5},
    {"id": "c2", "name": "Dark Magician", "attack": 2500, "defense": 2100, "cost": 4},
    {"id": "c3", "name": "Blue-Eyes", "attack": 3000, "defense": 2500, "cost": 6},
    {"id": "c4", "name": "Summoned Skull", "attack": 2600, "defense": 1500, "cost": 3},
    {"id": "c5", "name": "Celtic Guardian", "attack": 1400, "defense": 1200, "cost": 1},
    {"id": "c6", "name": "Mystical Elf", "attack": 800, "defense": 2000, "cost": 1},
    {"id": "c7", "name": "Beaver Warrior", "attack": 1200, "defense": 1500, "cost": 2},
    {"id": "c8", "name": "Rogue Doll", "attack": 1600, "defense": 1000, "cost": 2},
    {"id": "c9", "name": "Gemini Elf", "attack": 1900, "defense": 900, "cost": 3},
    {"id": "c10", "name": "Witch of the Black Forest", "attack": 1100, "defense": 1200, "cost": 2},
]

SHOP = [
    {"id": "s1", "name": "Hint Card", "effect": "reveal_opponent_hand", "price": 2},
    {"id": "s2", "name": "Power Boost", "effect": "double_attack_next", "price": 3},
    {"id": "s3", "name": "Shield Spell", "effect": "negate_next_attack", "price": 4},
    {"id": "s4", "name": "Deep Search", "effect": "draw_3_keep_best", "price": 8},
    {"id": "s5", "name": "Expert Policy", "effect": "optimal_play_recommended", "price": 20},
]


@dataclass
class GameState:
    player_hp: int = 8000
    opponent_hp: int = 8000
    player_hand: list[dict] = field(default_factory=list)
    opponent_hand: list[dict] = field(default_factory=list)
    player_field: list[dict] = field(default_factory=list)
    opponent_field: list[dict] = field(default_factory=list)
    player_credits: int = 30
    opponent_credits: int = 30
    turn: int = 0
    actions_remaining: int = ACTION_BUDGET


# --- Opponent Strategies ---

class OpponentStrategy:
    def choose_actions(self, state: GameState, rng: random.Random) -> list[dict]:
        raise NotImplementedError


class PassiveOpponent(OpponentStrategy):
    def choose_actions(self, state: GameState, rng: random.Random) -> list[dict]:
        actions = []
        playable = [c for c in state.opponent_hand if c["cost"] <= state.opponent_credits]
        if playable:
            actions.append({"type": "play_card", "card": playable[0]})
        if state.opponent_field and not state.player_field:
            actions.append({"type": "attack_direct", "card": state.opponent_field[0]})
        elif state.opponent_field and state.player_field:
            actions.append({"type": "attack", "card": state.opponent_field[0],
                           "target": state.player_field[0]})
        return actions[:ACTION_BUDGET]


class AggressiveOpponent(OpponentStrategy):
    def choose_actions(self, state: GameState, rng: random.Random) -> list[dict]:
        actions = []
        for item in SHOP:
            if item["effect"] == "double_attack_next" and item["price"] <= state.opponent_credits:
                actions.append({"type": "buy", "item": item})
                break
        playable = [c for c in state.opponent_hand if c["cost"] <= state.opponent_credits]
        if playable:
            best = max(playable, key=lambda c: c["attack"])
            actions.append({"type": "play_card", "card": best})
        if state.opponent_field:
            attacker = max(state.opponent_field, key=lambda c: c["attack"])
            if state.player_field:
                target = max(state.player_field, key=lambda c: c["defense"])
                actions.append({"type": "attack", "card": attacker, "target": target})
            else:
                actions.append({"type": "attack_direct", "card": attacker})
        return actions[:ACTION_BUDGET]


class DefensiveOpponent(OpponentStrategy):
    def choose_actions(self, state: GameState, rng: random.Random) -> list[dict]:
        actions = []
        for item in SHOP:
            if item["effect"] == "negate_next_attack" and item["price"] <= state.opponent_credits:
                actions.append({"type": "buy", "item": item})
                break
        playable = [c for c in state.opponent_hand if c["cost"] <= state.opponent_credits]
        if playable:
            best = max(playable, key=lambda c: c["defense"])
            actions.append({"type": "play_card", "card": best})
        if state.opponent_field:
            attacker = state.opponent_field[0]
            if state.player_field:
                target = state.player_field[0]
                if attacker["attack"] > target["defense"] * 1.2:
                    actions.append({"type": "attack", "card": attacker, "target": target})
            elif state.opponent_credits < 5:
                actions.append({"type": "attack_direct", "card": attacker})
        return actions[:ACTION_BUDGET]


class EconomicOpponent(OpponentStrategy):
    def choose_actions(self, state: GameState, rng: random.Random) -> list[dict]:
        actions = []
        for item in reversed(SHOP):
            if item["price"] <= state.opponent_credits and item["price"] >= 4:
                actions.append({"type": "buy", "item": item})
                break
        playable = [c for c in state.opponent_hand if c["cost"] <= state.opponent_credits]
        if playable:
            cheapest = min(playable, key=lambda c: c["cost"])
            actions.append({"type": "play_card", "card": cheapest})
        if state.opponent_field:
            attacker = state.opponent_field[0]
            if state.player_field:
                target = max(state.player_field, key=lambda c: c["attack"])
                if attacker["attack"] > target["defense"]:
                    actions.append({"type": "attack", "card": attacker, "target": target})
            elif state.opponent_credits < 5:
                actions.append({"type": "attack_direct", "card": attacker})
        return actions[:ACTION_BUDGET]


OPPONENT_STRATEGIES = {
    "passive": PassiveOpponent,
    "aggressive": AggressiveOpponent,
    "defensive": DefensiveOpponent,
    "economic": EconomicOpponent,
}


class YGOEnv:
    """Deterministic Yu-Gi-Oh environment with equal action budgets."""

    def __init__(self, seed: int = 42, opponent: str = "passive"):
        self.rng = random.Random(seed)
        self.opponent_strategy = OPPONENT_STRATEGIES.get(opponent, PassiveOpponent)()
        self.opponent_name = opponent
        self.state = GameState()
        self.history: list[dict] = []
        self._double_attack_next = False
        self._shield_next = False
        self._opp_double_attack = False
        self._opp_shield = False
        self._phase = "player"  # "player" or "opponent"
        self.reset()

    def reset(self):
        self.state = GameState()
        self.state.player_hand = self.rng.sample(CARDS, 5)
        self.state.opponent_hand = self.rng.sample(CARDS, 5)
        self.state.turn = 1
        self.state.actions_remaining = ACTION_BUDGET
        self._phase = "player"
        self.history = []
        self._double_attack_next = False
        self._shield_next = False
        self._opp_double_attack = False
        self._opp_shield = False
        return self._obs()

    def _obs(self) -> dict:
        return {
            "player_hp": self.state.player_hp,
            "opponent_hp": self.state.opponent_hp,
            "player_hand": [c["name"] for c in self.state.player_hand],
            "opponent_hand_count": len(self.state.opponent_hand),
            "player_field": [c["name"] for c in self.state.player_field],
            "opponent_field": [c["name"] for c in self.state.opponent_field],
            "player_credits": self.state.player_credits,
            "opponent_credits": self.state.opponent_credits,
            "turn": self.state.turn,
            "actions_remaining": self.state.actions_remaining,
            "phase": self._phase,
            "opponent": self.opponent_name,
        }

    def available_actions(self) -> list[dict]:
        if self._phase == "opponent":
            return [{"type": "wait", "cost": 0, "estimated_value": 0}]

        actions = []
        for card in self.state.player_hand:
            if card["cost"] <= self.state.player_credits:
                actions.append({
                    "type": "play_card",
                    "card": card,
                    "cost": card["cost"],
                    "estimated_value": card["attack"] / 1000,
                })
        for item in SHOP:
            if item["price"] <= self.state.player_credits:
                actions.append({
                    "type": "buy",
                    "item": item,
                    "cost": item["price"],
                    "estimated_value": item["price"] * 0.8,
                })
        if self.state.player_field:
            if self.state.opponent_field:
                actions.append({
                    "type": "attack",
                    "card": self.state.player_field[0],
                    "cost": 0,
                    "estimated_value": self.state.player_field[0]["attack"] / 1000,
                })
            else:
                actions.append({
                    "type": "attack",
                    "card": self.state.player_field[0],
                    "cost": 0,
                    "estimated_value": self.state.player_field[0]["attack"] / 1000,
                })
        actions.append({"type": "end_turn", "cost": 0, "estimated_value": 0})
        return actions

    def _apply_attack(self, card: dict, target: dict | None, is_opponent: bool) -> float:
        """Apply an attack, return damage dealt."""
        atk = card["attack"]
        if is_opponent:
            if self._opp_double_attack:
                atk *= 2
            self._opp_double_attack = False
            shield = self._shield_next
            if shield:
                self._shield_next = False
                return 0
        else:
            if self._double_attack_next:
                atk *= 2
            self._double_attack_next = False
            shield = self._opp_shield
            if shield:
                self._opp_shield = False
                return 0

        if target:
            if atk > target["defense"]:
                if is_opponent:
                    self.state.player_field.remove(target)
                else:
                    self.state.opponent_field.remove(target)
                damage = atk - target["defense"]
                if is_opponent:
                    self.state.player_hp -= damage
                else:
                    self.state.opponent_hp -= damage
                return damage
            else:
                damage = target["defense"] - atk
                if is_opponent:
                    self.state.player_hp -= damage
                else:
                    self.state.opponent_hp -= damage
                return -damage
        else:
            if is_opponent:
                self.state.player_hp -= atk
            else:
                self.state.opponent_hp -= atk
            return atk

    def _apply_action(self, action: dict, is_opponent: bool) -> float:
        """Apply a single action, return reward."""
        hand = self.state.opponent_hand if is_opponent else self.state.player_hand
        field = self.state.opponent_field if is_opponent else self.state.player_field
        credits = self.state.opponent_credits if is_opponent else self.state.player_credits

        if action["type"] == "play_card":
            card = action["card"]
            if card["cost"] <= credits:
                if is_opponent:
                    self.state.opponent_credits -= card["cost"]
                else:
                    self.state.player_credits -= card["cost"]
                hand.remove(card)
                field.append(card)
                return 0.1

        elif action["type"] == "buy":
            item = action["item"]
            if item["price"] <= credits:
                if is_opponent:
                    self.state.opponent_credits -= item["price"]
                else:
                    self.state.player_credits -= item["price"]
                if item["effect"] == "double_attack_next":
                    if is_opponent:
                        self._opp_double_attack = True
                    else:
                        self._double_attack_next = True
                elif item["effect"] == "negate_next_attack":
                    if is_opponent:
                        self._opp_shield = True
                    else:
                        self._shield_next = True
                elif item["effect"] == "draw_3_keep_best":
                    for _ in range(3):
                        if len(hand) < 7:
                            hand.append(self.rng.choice(CARDS))
                return 0.05

        elif action["type"] == "attack":
            card = action["card"]
            target = action.get("target")
            damage = self._apply_attack(card, target, is_opponent)
            return damage / 1000

        elif action["type"] == "attack_direct":
            card = action["card"]
            damage = self._apply_attack(card, None, is_opponent)
            return damage / 1000

        return 0.0

    def _apply_opponent_turn(self):
        """Opponent takes their budget of actions."""
        actions = self.opponent_strategy.choose_actions(self.state, self.rng)
        for action in actions[:ACTION_BUDGET]:
            self._apply_action(action, is_opponent=True)

    def step(self, action: dict) -> tuple[dict, float, bool, dict]:
        """Execute one action. Returns (obs, reward, done, info)."""
        reward = 0.0
        info = {"events": []}

        if action["type"] == "wait":
            # Opponent's turn, auto-advance
            pass

        elif action["type"] == "end_turn":
            self._phase = "opponent"
            self._apply_opponent_turn()
            self.state.turn += 1
            self.state.actions_remaining = ACTION_BUDGET
            self._phase = "player"
            # Draw a card
            new_card = self.rng.choice(CARDS)
            if len(self.state.player_hand) < 7:
                self.state.player_hand.append(new_card)

        else:
            reward = self._apply_action(action, is_opponent=False)
            self.state.actions_remaining -= 1
            if self.state.actions_remaining <= 0:
                # Auto end turn if budget exhausted
                self._phase = "opponent"
                self._apply_opponent_turn()
                self.state.turn += 1
                self.state.actions_remaining = ACTION_BUDGET
                self._phase = "player"
                new_card = self.rng.choice(CARDS)
                if len(self.state.player_hand) < 7:
                    self.state.player_hand.append(new_card)

        self.history.append({"action": action, "reward": reward, **info})
        done = self.state.player_hp <= 0 or self.state.opponent_hp <= 0 or self.state.turn > 20
        return self._obs(), reward, done, info
