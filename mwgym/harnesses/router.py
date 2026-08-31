"""DynamicRouter — picks the right genome/harness for each task.

Enhanced with LiveLLM market intelligence:
- Fetches real-time pricing, promotions, and capabilities from LiveLLM
- Builds DecisionOptions with verified economic data
- Routes to the best model based on cost/quality tradeoffs
- Logs stale-vs-live comparisons for auditability

Routes between:
- direct-fast: simple text output tasks (cheaper, faster)
- fast-bundle: multi-file or structured output tasks (produces artifacts)

When LiveLLM is available, the router can also pick specific models based on
current market conditions (e.g., a promoted model that's cheaper than the default).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from ..schema.genome import WorkerGenome
from ..harnesses.direct import DirectAdapter
from ..harnesses.fast import FastExecutor
from .base import HarnessInstance, HarnessRun

# Lazy import to avoid circular deps
_MarketClient = None
_MarketSnapshot = None
_ModelRoute = None


def _get_market_types():
    global _MarketClient, _MarketSnapshot, _ModelRoute
    if _MarketClient is None:
        from ..market import MarketClient, MarketSnapshot, ModelRoute
        _MarketClient = MarketClient
        _MarketSnapshot = MarketSnapshot
        _ModelRoute = ModelRoute


# Patterns that indicate we need structured output (fast-bundle)
COMPLEX_PATTERNS = [
    r"write.*json",
    r"write.*yaml",
    r"write.*multiple",
    r"write.*list",
    r"create.*file.*and",
    r"write.*and.*write",
    r"actionbundle",
    r"structured",
]

# Patterns that indicate simple text output (direct-fast)
SIMPLE_PATTERNS = [
    r"write.*word",
    r"write.*number",
    r"write.*text",
    r"write.*the word",
    r"write.*heading",
    r"write.*code",
    r"^write\s+\w+$",
]


@dataclass
class MarketContext:
    """Economic context for a routing decision."""
    source: str = ""  # "livellm" or "stale"
    model: str = ""
    provider: str = ""
    input_per_1m: float | None = None
    output_per_1m: float | None = None
    effective_input_cost: float | None = None  # after promotions
    promotion: dict | None = None
    quality_tier: str | None = None
    context_tokens: int | None = None
    freshness: str = ""
    confidence: float | None = None


@dataclass
class RouterDecision:
    genome: str
    reason: str
    confidence: float
    market: MarketContext = field(default_factory=MarketContext)
    stale_comparison: dict | None = None  # what we would have picked without LiveLLM


class DynamicRouter:
    """Classifies tasks and routes to the appropriate genome.

    When a MarketClient is provided, routing decisions incorporate real-time
    pricing data from LiveLLM instead of hardcoded cost assumptions.
    """

    def __init__(self, market_client=None):
        self.direct = DirectAdapter()
        self.fast = FastExecutor()
        self.decisions: list[dict] = []
        self.market = market_client

    def _build_market_options(self, task: str) -> list[tuple[str, MarketContext]]:
        """Fetch market data and build economically-informed options.

        Always uses effective_input_per_1m (after subscription discounts)
        so the router never compares raw prices.
        """
        if self.market is None:
            return []

        snap = self.market.fetch()
        if snap is None:
            return []

        options = []
        for name, routes in snap.models.items():
            for route in routes:
                # Skip models without pricing
                if route.input_per_1m is None:
                    continue

                ctx = MarketContext(
                    source="livellm",
                    model=name,
                    provider=route.provider,
                    input_per_1m=route.effective_input_per_1m or route.input_per_1m,
                    output_per_1m=route.effective_output_per_1m or route.output_per_1m,
                    effective_input_cost=route.effective_input_per_1m,
                    promotion=route.promotion,
                    quality_tier=route.quality_tier,
                    context_tokens=route.context_tokens,
                    confidence=route.freshness.get("confidence") if route.freshness else None,
                )
                if route.freshness:
                    ctx.freshness = route.freshness.get("as_of", "")

                options.append((name, ctx))

        return options

    # MiMo V2.5 is the reference model — best all-around for agent work
    REFERENCE_MODEL = "MiMo V2.5"

    # Models that beat MiMo on specific axes (provider:reason)
    BEATS_MIMO = {
        "Gemini 2.5 Pro": "context",   # 2M ctx vs 1M
        "Gemini 2.5 Flash": "speed",   # faster inference
    }

    def _score_model(self, name: str, route) -> float:
        """Score a model for agent work. Higher = better.

        Considers: actual cost (including subscription discounts like Go's 6x),
        context, quality tier, benchmarks, multimodal capability.
        MiMo V2.5 is the baseline at 100.

        ALWAYS uses effective_input_per_1m — never raw input_per_1m.
        This is the field that applies subscription multipliers.
        """
        score = 0.0

        # Use the effective price (after subscription discounts)
        effective_input = route.effective_input_per_1m if hasattr(route, 'effective_input_per_1m') else (route.go_effective_input_per_1m or route.input_per_1m)

        # Cached input cost (dominant cost in agent loops)
        cached = route.cached_input_per_1m
        if cached is not None:
            # MiMo's cached rate is $0.0028/M — baseline
            if cached <= 0.003:
                score += 40  # excellent cached rate
            elif cached <= 0.01:
                score += 30
            elif cached <= 0.03:
                score += 20
            else:
                score += 10

        # Effective input cost (accounts for Go 6x multiplier)
        if effective_input is not None:
            if effective_input <= 0.03:
                score += 15  # Go-discounted MiMo tier
            elif effective_input <= 0.08:
                score += 10
            elif effective_input <= 0.15:
                score += 5

        # Subscription value (Go gives $60/mo for $10/mo)
        if route.usage_value_usd_month and route.subscription_monthly_usd:
            ratio = route.usage_value_usd_month / route.subscription_monthly_usd
            if ratio >= 5:
                score += 10  # 6x multiplier
            elif ratio >= 3:
                score += 5

        # Context window (bigger = better for agent work)
        ctx = route.context_tokens or 0
        if ctx >= 1_000_000:
            score += 25
        elif ctx >= 200_000:
            score += 20
        elif ctx >= 100_000:
            score += 15
        else:
            score += 5

        # Quality tier
        tier = route.quality_tier or ""
        if tier == "premium":
            score += 20
        elif tier == "balanced":
            score += 15
        elif tier == "fast":
            score += 10

        # Max output tokens
        max_out = route.max_output_tokens or 0
        if max_out >= 64_000:
            score += 10
        elif max_out >= 16_000:
            score += 5

        # Multimodal bonus (MiMo has this, most don't)
        modalities = route.modalities
        if isinstance(modalities, list) and len(modalities) > 1:
            score += 5
        elif isinstance(modalities, str) and modalities != "text":
            score += 5

        return score

    def _stale_default(self) -> tuple[str, MarketContext]:
        """What the router would pick without LiveLLM (hardcoded default)."""
        return (self.REFERENCE_MODEL, MarketContext(
            source="stale",
            model=self.REFERENCE_MODEL,
            provider="opencode-go",
            input_per_1m=None,
            quality_tier=None,
        ))

    def classify(self, task: str) -> RouterDecision:
        """Determine which genome should handle this task.

        Without LiveLLM: uses regex patterns + hardcoded defaults.
        With LiveLLM: uses real market data to pick the best model.

        Default model is MiMo V2.5 — best all-around for agent work
        (1M context, multimodal, strong reasoning, $0.0028/M cached).
        Only deviates when market data shows a genuinely better option.
        """
        task_lower = task.lower()

        # Check task complexity
        is_complex = False
        for pat in COMPLEX_PATTERNS:
            if re.search(pat, task_lower):
                is_complex = True
                break

        is_simple = False
        for pat in SIMPLE_PATTERNS:
            if re.search(pat, task_lower):
                is_simple = True
                break

        # Stale decision (what we'd pick without market data)
        stale_model, stale_ctx = self._stale_default()
        if is_complex:
            stale_model = "fast-bundle"
            stale_ctx = MarketContext(source="stale", model="fast-bundle")

        # Market-aware decision
        market_options = self._build_market_options(task)

        if not market_options:
            # No market data available — fall back to stale
            genome = "fast-bundle" if is_complex else "direct-fast"
            reason = "no market data" if self.market else "no market client configured"
            if is_simple:
                genome = "direct-fast"
                reason = "matched simple pattern"
            elif is_complex:
                reason = "matched complex pattern"
            else:
                reason = "defaulting to MiMo V2.5 (no market data)"

            return RouterDecision(
                genome=genome,
                reason=reason,
                confidence=0.5 if not is_simple and not is_complex else 0.8,
                market=stale_ctx,
            )

        # Score all models and pick the best
        scored = []
        for name, ctx in market_options:
            route = None
            for r in self.market.fetch().models.get(name, []):
                if r.provider == ctx.provider:
                    route = r
                    break
            if route:
                score = self._score_model(name, route)
                scored.append((name, ctx, score))

        scored.sort(key=lambda x: x[2], reverse=True)

        if is_simple:
            # Simple tasks: MiMo is fine (it's fast and cheap on cached)
            best_name, best_ctx, best_score = scored[0]
            genome = "direct-fast"
            reason = f"best scored: {best_name} (score={best_score:.0f})"
        elif is_complex:
            # Complex tasks: need big context — prefer models with >500K ctx
            big_ctx = [(n, c, s) for n, c, s in scored if (c.context_tokens or 0) >= 500_000]
            if big_ctx:
                best_name, best_ctx, best_score = big_ctx[0]
            else:
                best_name, best_ctx, best_score = scored[0]
            genome = "fast-bundle"
            reason = f"best scored for complex work: {best_name} (score={best_score:.0f})"
        else:
            # Default: best overall score
            best_name, best_ctx, best_score = scored[0]
            genome = "direct-fast"
            reason = f"best scored: {best_name} (score={best_score:.0f})"

        # Build stale comparison
        stale_comparison = None
        if best_name != stale_model:
            stale_comparison = {
                "without_livellm": stale_model,
                "with_livellm": best_name,
                "reason": reason,
                "promotion_active": best_ctx.promotion is not None,
            }

        return RouterDecision(
            genome=genome,
            reason=reason,
            confidence=0.85 if best_ctx.confidence and best_ctx.confidence > 0.9 else 0.7,
            market=best_ctx,
            stale_comparison=stale_comparison,
        )

    async def run(self, task: str, workspace: str, run_id: str = "") -> dict:
        """Route and execute a task with market-aware intelligence."""
        decision = self.classify(task)

        genome = WorkerGenome.direct_fast() if decision.genome == "direct-fast" else WorkerGenome(
            id="fast-bundle", harness_kind="fast",
            thinking="disabled", memory_enabled=False,
            max_model_requests=1, max_tool_calls=10, max_wall_seconds=30, max_usd=0.002,
        )

        # If market data selected a specific model, note it in the genome
        if decision.market.model and decision.market.source == "livellm":
            genome = WorkerGenome(
                id=f"market-{decision.market.model}",
                harness_kind=genome.harness_kind,
                model_id=decision.market.model,
                thinking="disabled", memory_enabled=False,
                max_model_requests=1, max_tool_calls=10, max_wall_seconds=30,
                max_usd=decision.market.effective_input_cost * 10 or 0.002,
            )

        instance = HarnessInstance(harness=decision.genome, worker_id=f"router-{run_id}")

        if decision.genome == "direct-fast":
            result = await self.direct.run(instance, task, workspace)
        else:
            result = self.fast.run(instance, task, workspace)

        self.decisions.append({
            "run_id": run_id,
            "task": task[:60],
            "routed_to": decision.genome,
            "model": decision.market.model,
            "provider": decision.market.provider,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "success": result.ok,
            "market_source": decision.market.source,
            "input_per_1m": decision.market.input_per_1m,
            "promotion": decision.market.promotion,
            "stale_comparison": decision.stale_comparison,
        })

        return {
            "run_id": run_id,
            "routed_to": decision.genome,
            "model": decision.market.model,
            "provider": decision.market.provider,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "success": result.ok,
            "output": result.output,
            "artifacts": result.artifacts,
            "model_calls": len(result.model_calls),
            "total_tokens": result.total_tokens,
            "duration_ms": result.duration_ms,
            "cost_usd": result.cost_usd,
            "market_context": {
                "source": decision.market.source,
                "model": decision.market.model,
                "input_per_1m": decision.market.input_per_1m,
                "promotion": decision.market.promotion,
                "freshness": decision.market.freshness,
            },
            "stale_comparison": decision.stale_comparison,
        }
