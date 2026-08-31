"""YGO Environment Adapter — wraps our YGO env to match ygoenv interface.

Per spec Section 5: use the pinned sbl1996/ygo-agent ygoenv.
Since the C++ extension can't be built on this system, we create a
thin adapter that provides the same interface.

This is NOT the canonical ygoenv — it's a temporary bridge until
the C++ extension is available.
"""
from __future__ import annotations

import random
from typing import Any

from .env import YGOEnv, CARDS, SHOP, OPPONENT_STRATEGIES


class YGOEnvAdapter:
    """Adapter that wraps our YGO env to match ygoenv interface.

    Provides:
    - reset() -> observation
    - step(action) -> (observation, reward, done, info)
    - observation_space
    - action_space
    - legal_actions()

    This allows MWGym to test the architecture without the C++ extension.
    """

    def __init__(self, seed: int = 42, opponent: str = "passive"):
        self.env = YGOEnv(seed=seed, opponent=opponent)
        self.seed = seed
        self.opponent = opponent
        self._observation_space = None
        self._action_space = None

    @property
    def observation_space(self):
        """Observation space matching ygoenv interface."""
        if self._observation_space is None:
            # Simple observation: player_hp, opponent_hp, credits, hand_size, field_size
            self._observation_space = _BoxSpace(low=0, high=10000, shape=(6,))
        return self._observation_space

    @property
    def action_space(self):
        """Action space matching ygoenv interface."""
        if self._action_space is None:
            # Actions: play_card_0-4, buy_0-4, attack, end_turn = 11 possible actions
            self._action_space = _DiscreteSpace(n=11)
        return self._action_space

    def reset(self):
        """Reset environment, return observation."""
        obs = self.env.reset()
        return self._obs_to_array(obs)

    def step(self, action: int):
        """Take action, return (obs, reward, done, info)."""
        # Convert int action to action dict
        action_dict = self._int_to_action(action)
        obs, reward, done, info = self.env.step(action_dict)
        return self._obs_to_array(obs), reward, done, info

    def legal_actions(self) -> list[int]:
        """Return list of legal action indices."""
        actions = self.env.available_actions()
        legal = []
        for i, action in enumerate(actions):
            if action["type"] == "play_card":
                legal.append(i)
            elif action["type"] == "buy":
                legal.append(5 + SHOP.index(action["item"]) if action["item"] in SHOP else -1)
            elif action["type"] == "attack":
                legal.append(10)
            elif action["type"] == "end_turn":
                legal.append(10)  # end_turn overlaps with attack
        return [a for a in legal if 0 <= a < 11]

    def _obs_to_array(self, obs: dict) -> Any:
        """Convert observation dict to numpy array."""
        import numpy as np
        return np.array([
            obs.get("player_hp", 0),
            obs.get("opponent_hp", 0),
            obs.get("player_credits", 0),
            len(obs.get("player_hand", [])),
            len(obs.get("player_field", [])),
            obs.get("turn", 0),
        ], dtype=np.float32)

    def _int_to_action(self, action: int) -> dict:
        """Convert integer action to action dict."""
        actions = self.env.available_actions()
        if action < len(actions):
            return actions[action]
        return {"type": "end_turn"}

    def close(self):
        """Close environment."""
        pass


class _BoxSpace:
    """Minimal Box space for observation."""
    def __init__(self, low=0, high=1, shape=(1,)):
        self.low = low
        self.high = high
        self.shape = shape

    def sample(self):
        import numpy as np
        return np.random.uniform(self.low, self.high, self.shape)


class _DiscreteSpace:
    """Minimal Discrete space for actions."""
    def __init__(self, n=2):
        self.n = n

    def sample(self):
        return random.randint(0, self.n - 1)


def make(seed: int = 42, opponent: str = "passive") -> YGOEnvAdapter:
    """Create YGO environment adapter."""
    return YGOEnvAdapter(seed=seed, opponent=opponent)
