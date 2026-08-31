"""YGO World — deterministic Yu-Gi-Oh environment for testing resource allocation.

Closed world, perfect information, synthetic economics.
Tests L0 (reasoning) and L1 (execution) allocation.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


# Cards
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

# Synthetic shop items (x402 purchases)
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
    credits: int = 30
    turn: int = 0
    phase: str = "draw"  # draw, main, battle, end


class YGOEnv:
    """Deterministic Yu-Gi-Oh environment."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.state = GameState()
        self.history: list[dict] = []
        self.reset()

    def reset(self):
        self.state = GameState()
        self.state.player_hand = self.rng.sample(CARDS, 5)
        self.state.opponent_hand = self.rng.sample(CARDS, 5)
        self.state.turn = 1
        self.history = []
        return self._obs()

    def _obs(self) -> dict:
        return {
            "player_hp": self.state.player_hp,
            "opponent_hp": self.state.opponent_hp,
            "player_hand": [c["name"] for c in self.state.player_hand],
            "opponent_hand_count": len(self.state.opponent_hand),
            "player_field": [c["name"] for c in self.state.player_field],
            "opponent_field": [c["name"] for c in self.state.opponent_field],
            "credits": self.state.credits,
            "turn": self.state.turn,
        }

    def available_actions(self) -> list[dict]:
        actions = []
        # Can play cards from hand
        for card in self.state.player_hand:
            if card["cost"] <= self.state.credits:
                actions.append({
                    "type": "play_card",
                    "card": card,
                    "cost": card["cost"],
                    "estimated_value": card["attack"] / 1000,
                })
        # Can buy from shop
        for item in SHOP:
            if item["price"] <= self.state.credits:
                actions.append({
                    "type": "buy",
                    "item": item,
                    "cost": item["price"],
                    "estimated_value": item["price"] * 0.8,
                })
        # Can attack
        if self.state.player_field:
            actions.append({
                "type": "attack",
                "card": self.state.player_field[0],
                "cost": 0,
                "estimated_value": self.state.player_field[0]["attack"] / 1000,
            })
        # Can end turn
        actions.append({"type": "end_turn", "cost": 0, "estimated_value": 0})
        return actions

    def step(self, action: dict) -> tuple[dict, float, bool, dict]:
        """Execute action, return (obs, reward, done, info)."""
        reward = 0.0
        info = {"events": []}

        if action["type"] == "play_card":
            card = action["card"]
            self.state.credits -= card["cost"]
            self.state.player_hand.remove(card)
            self.state.player_field.append(card)
            reward = 0.1  # small reward for playing
            info["events"].append(f"Played {card['name']}")

        elif action["type"] == "buy":
            item = action["item"]
            self.state.credits -= item["price"]
            reward = 0.05  # small reward for buying
            info["events"].append(f"Bought {item['name']} for ${item['price']}")

        elif action["type"] == "attack":
            card = action["card"]
            if self.state.opponent_field:
                defender = self.state.opponent_field[0]
                if card["attack"] > defender["defense"]:
                    self.state.opponent_field.remove(defender)
                    damage = card["attack"] - defender["defense"]
                    self.state.opponent_hp -= damage
                    reward = damage / 1000
                    info["events"].append(f"{card['name']} destroyed {defender['name']}")
                else:
                    damage = defender["defense"] - card["attack"]
                    self.state.player_hp -= damage
                    reward = -damage / 1000
                    info["events"].append(f"{card['name']} failed to destroy {defender['name']}")
            else:
                self.state.opponent_hp -= card["attack"]
                reward = card["attack"] / 1000
                info["events"].append(f"{card['name']} direct attack for {card['attack']}")

        elif action["type"] == "end_turn":
            self.state.turn += 1
            # Opponent plays a card
            if self.state.opponent_hand:
                opp_card = self.state.opponent_hand.pop(0)
                self.state.opponent_field.append(opp_card)
            # Draw a card
            if CARDS:
                new_card = self.rng.choice(CARDS)
                if len(self.state.player_hand) < 7:
                    self.state.player_hand.append(new_card)

        self.history.append({"action": action, "reward": reward, **info})
        done = self.state.player_hp <= 0 or self.state.opponent_hp <= 0 or self.state.turn > 20
        return self._obs(), reward, done, info
