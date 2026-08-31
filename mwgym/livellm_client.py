"""LiveLLM client — real-time market data for StackOracle.

Fetches live pricing, promotions, free-tier info from LiveLLM.
Provides economic truth for routing decisions.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field


LIVELLM_URL = "http://localhost:3847"


@dataclass
class ModelRoute:
    """A route to a model through a provider."""
    provider: str = ""
    model_id: str = ""
    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    cached_input_per_1m: float = 0.0
    context_tokens: int = 0
    quality_tier: str = ""  # fast, balanced, strong
    freshness: dict = field(default_factory=dict)

    @property
    def effective_cost(self, tokens: int = 1000) -> float:
        """Effective cost for N input tokens."""
        return self.input_per_1m * tokens / 1_000_000


@dataclass
class MarketSnapshot:
    """Point-in-time market data from LiveLLM."""
    models: dict[str, list[ModelRoute]] = field(default_factory=dict)
    generated_at: str = ""
    as_of: str = ""
    source: str = "livellm"


class LiveLLMClient:
    """Client for LiveLLM market data."""

    def __init__(self, base_url: str = LIVELLM_URL):
        self.base_url = base_url
        self._cache: MarketSnapshot | None = None
        self._cache_time: float = 0
        self._cache_ttl: float = 300  # 5 minutes

    def fetch_market(self) -> MarketSnapshot | None:
        """Fetch current market data from LiveLLM."""
        if self._cache and (time.time() - self._cache_time) < self._cache_ttl:
            return self._cache

        try:
            url = f"{self.base_url}/v1/market"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())

            models = {}
            for m in data.get("models", []):
                model_name = m.get("model", "")
                routes = []
                for r in m.get("routes", []):
                    route = ModelRoute(
                        provider=r.get("provider", ""),
                        model_id=model_name,
                        input_per_1m=r.get("input", 0),
                        output_per_1m=r.get("output", 0),
                        cached_input_per_1m=r.get("cached_input", 0),
                        context_tokens=r.get("context_tokens", 0),
                        freshness=r.get("freshness", {}),
                    )
                    routes.append(route)
                models[model_name] = routes

            snapshot = MarketSnapshot(
                models=models,
                generated_at=data.get("generated_at", ""),
                as_of=data.get("as_of", ""),
                source="livellm",
            )
            self._cache = snapshot
            self._cache_time = time.time()
            return snapshot

        except Exception as e:
            print(f"LiveLLM fetch failed: {e}")
            return self._cache

    def get_cheapest(self, task_family: str = "") -> ModelRoute | None:
        """Get the cheapest available model."""
        snapshot = self.fetch_market()
        if not snapshot:
            return None

        cheapest = None
        for model_name, routes in snapshot.models.items():
            for route in routes:
                if route.input_per_1m <= 0:  # free
                    if cheapest is None or route.input_per_1m < cheapest.input_per_1m:
                        cheapest = route
        return cheapest

    def get_best_value(self, task_family: str = "") -> ModelRoute | None:
        """Get the best value model (quality/cost ratio)."""
        snapshot = self.fetch_market()
        if not snapshot:
            return None

        # For now, return cheapest free model
        return self.get_cheapest(task_family)

    def price_change_detected(self) -> list[dict]:
        """Check if prices changed since last fetch."""
        # Compare current cache with fresh fetch
        old_as_of = self._cache.as_of if self._cache else ""
        new_snapshot = self.fetch_market()
        if new_snapshot and new_snapshot.as_of != old_as_of:
            return [{"type": "price_update", "as_of": new_snapshot.as_of}]
        return []
