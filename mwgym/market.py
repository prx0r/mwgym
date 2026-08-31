"""MarketClient — verified economic intelligence for autonomous agents.

Pricing is not a scalar. The same model has:
  - list_price: provider/token accounting price
  - amortized_price: subscription fee divided across fully-utilized included value
  - marginal_price: what the NEXT request costs given current subscription/quota state

This module models all three. It includes:
  - Subscription plan registry with model-specific included usage values
  - Temporal promotions stored separately from base facts
  - Reconciliation validator that reproduces published request limits
  - Verification states including conflict detection
  - Source observation freshness tracking

Source: OpenCode Go docs (opencode.ai/docs/go/), verified August 31, 2026.
Reference: /root/livellm/refs/pricing-complexity-ref.md
"""
from __future__ import annotations

import json
import os
import re
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# ─── Verification States ─────────────────────────────────────────────────────

class VerificationState(Enum):
    """How confident we are in a pricing fact."""
    CANDIDATE = "candidate"           # discovered but not yet verified
    VERIFIED = "verified"             # confirmed against official source
    RECONCILED = "reconciled"         # verified AND math matches published limits
    CONFLICTING_SOURCES = "conflicting_official_sources"  # official surfaces disagree
    EXPIRED = "expired"               # no longer observed on fresh fetches


# ─── Subscription Economics (permanent plan facts) ───────────────────────────

@dataclass
class SubscriptionEconomics:
    """Permanent plan economics — NOT affected by temporary promotions."""
    provider: str
    plan: str
    model_id: str
    subscription_fee_usd: float
    included_usage_usd: float
    base_value_multiple: float  # DERIVED: included / fee — never scrape directly
    evidence_id: str = ""
    observed_at: str = ""


# ─── Usage Promotions (temporal facts) ──────────────────────────────────────

@dataclass
class UsagePromotion:
    """A temporary usage-limit modification — stored SEPARATELY from base facts.

    Never mutate subscription.included_usage because a banner appeared.
    Instead, store the promotion with its scope, validity, and verification state.
    """
    provider: str
    plan: str
    model_id: str
    promotion_type: str  # "usage_limit_multiplier", "price_discount"
    multiplier: float = 1.0
    scope: list[str] = field(default_factory=list)  # ["5h"], ["5h", "week", "month"], or ["unknown"]
    valid_from: str = ""
    valid_to: str = ""
    discovered_at: str = ""
    evidence_id: str = ""
    verification_state: str = VerificationState.CANDIDATE.value


# ─── Source Observation (freshness tracking) ─────────────────────────────────

@dataclass
class SourceObservation:
    """HTTP freshness metadata for a source fetch."""
    url: str = ""
    fetched_at: str = ""
    status: int = 0
    etag: str | None = None
    last_modified: str | None = None
    cache_control: str | None = None
    age: str | None = None
    raw_sha256: str = ""
    normalized_sha256: str = ""


# ─── Generic Promo Parser ────────────────────────────────────────────────────
# Matches "2× usage limits", "8x usage", etc. on a per-card basis.
# Do NOT search whole page — associate with nearest model card/DOM unit.

PROMO_RE = re.compile(
    r"(?P<multiplier>\d+(?:\.\d+)?)\s*[x×]\s*(?:usage(?:\s+limits?)?|limits?)",
    re.IGNORECASE,
)


# ─── OpenCode Go Plan ────────────────────────────────────────────────────────
# Source: opencode.ai/docs/go/
# The plan has rolling limits. Model usage is a SHARE of those limits.

@dataclass
class GoPlan:
    """OpenCode Go subscription plan — rolling limits."""
    monthly_fee_usd: float = 10.0
    limits: dict[str, float] = field(default_factory=lambda: {
        "5h": 12.0,
        "week": 30.0,
        "month": 60.0,
    })


# ─── Model Tariffs ───────────────────────────────────────────────────────────
# Each model has its own tariff within Go. The key insight: NOT all models
# get 6× value. OpenCode explicitly says some get lower multipliers because
# their provider economics differ.
#
# source_fact: model_usage_monthly_usd / plan.monthly_fee_usd = base_value_multiplier
# NOT a hardcoded multiplier.

@dataclass
class GoModelTariff:
    """Economic facts for one model on OpenCode Go."""
    model_id: str
    input_per_1m: float
    output_per_1m: float
    cached_read_per_1m: float
    model_usage_monthly_usd: float  # this model's share of the $60/mo pool
    context_tokens: int = 0
    max_output_tokens: int = 0
    modalities: str = "text"
    typical_request: dict = field(default_factory=dict)  # {input, cached_read, output}
    published_request_limits: dict = field(default_factory=dict)  # {5h, week, month}
    evidence_id: str = ""
    observed_at: str = ""


# Verified from opencode.ai/docs/go/ — August 31, 2026
GO_PLAN = GoPlan()

GO_TARIFFS: list[GoModelTariff] = [
    GoModelTariff(
        model_id="mimo-v2.5",
        input_per_1m=0.14,
        output_per_1m=0.28,
        cached_read_per_1m=0.0028,
        model_usage_monthly_usd=60.0,
        context_tokens=1_000_000,
        max_output_tokens=32_768,
        modalities="text",
        typical_request={"input": 830, "cached_read": 71_500, "output": 295},
        published_request_limits={"5h": 30_100, "week": 75_200, "month": 150_400},
    ),
    GoModelTariff(
        model_id="glm-5.3-flash",
        input_per_1m=0.15,
        output_per_1m=0.50,
        cached_read_per_1m=0.03,
        model_usage_monthly_usd=15.0,
        context_tokens=128_000,
        max_output_tokens=8_192,
        modalities="text",
        typical_request={"input": 1_000, "cached_read": 55_000, "output": 200},
        published_request_limits={"5h": 1_580, "week": 3_950, "month": 7_900},
    ),
    GoModelTariff(
        model_id="deepseek-v4-flash",
        input_per_1m=0.22,
        output_per_1m=0.66,
        cached_read_per_1m=0.007,
        model_usage_monthly_usd=30.0,
        context_tokens=1_000_000,
        max_output_tokens=32_768,
        modalities="text",
        typical_request={"input": 410, "cached_read": 71_300, "output": 310},
        published_request_limits={"5h": 11_400, "week": 28_600, "month": 57_200},
    ),
    GoModelTariff(
        model_id="deepseek-v4-flash",
        input_per_1m=0.44,  # peak pricing
        output_per_1m=1.32,
        cached_read_per_1m=0.014,
        model_usage_monthly_usd=30.0,
        context_tokens=1_000_000,
        max_output_tokens=32_768,
        modalities="text",
        typical_request={"input": 410, "cached_read": 71_300, "output": 310},
        published_request_limits={"5h": 11_400, "week": 28_600, "month": 57_200},
    ),
    GoModelTariff(
        model_id="kimi-k2.7",
        input_per_1m=0.95,
        output_per_1m=4.0,
        cached_read_per_1m=0.19,
        model_usage_monthly_usd=60.0,
        context_tokens=1_000_000,
        max_output_tokens=32_768,
        modalities="text",
        typical_request={"input": 1_000, "cached_read": 55_000, "output": 200},
        published_request_limits={"5h": 1_350, "week": 3_380, "month": 6_750},
    ),
    GoModelTariff(
        model_id="gpt-5.6-luna",
        input_per_1m=0.20,
        output_per_1m=1.20,
        cached_read_per_1m=0.02,
        model_usage_monthly_usd=60.0,
        context_tokens=256_000,
        max_output_tokens=32_768,
        modalities="text",
        typical_request={"input": 1_000, "cached_read": 55_000, "output": 200},
        published_request_limits={"5h": 2_050, "week": 5_100, "month": 10_250},
    ),
    GoModelTariff(
        model_id="hy3",
        input_per_1m=0.14,
        output_per_1m=0.58,
        cached_read_per_1m=0.035,
        model_usage_monthly_usd=60.0,
        context_tokens=1_000_000,
        max_output_tokens=32_768,
        modalities="text",
        typical_request={"input": 1_000, "cached_read": 55_000, "output": 200},
        published_request_limits={"5h": 5_400, "week": 13_500, "month": 27_000},
    ),
    GoModelTariff(
        model_id="muse-spark-1.2",
        input_per_1m=0.10,
        output_per_1m=0.20,
        cached_read_per_1m=0.002,
        model_usage_monthly_usd=60.0,
        context_tokens=128_000,
        max_output_tokens=32_768,
        modalities="text",
        typical_request={"input": 1_000, "cached_read": 55_000, "output": 200},
        published_request_limits={"5h": 45_300, "week": 113_300, "month": 226_600},
    ),
    GoModelTariff(
        model_id="qwen3.8-flash",
        input_per_1m=0.10,
        output_per_1m=0.40,
        cached_read_per_1m=0.01,
        model_usage_monthly_usd=60.0,
        context_tokens=1_000_000,
        max_output_tokens=32_768,
        modalities="text",
        typical_request={"input": 1_000, "cached_read": 55_000, "output": 200},
        published_request_limits={"5h": 7_600, "week": 19_000, "month": 38_000},
    ),
]

# Tariff lookup by model_id
_TARIFF_MAP: dict[str, GoModelTariff] = {t.model_id: t for t in GO_TARIFFS}

# DeepSeek peak hours: 01:00-04:00 and 06:00-10:00 UTC, Mon-Fri
# Source: opencode.ai/docs/go/
DEEPSEEK_PEAK_HOURS_UTC = [(1, 4), (6, 10)]


# ─── Promotions (temporal facts, NOT baked into base tariff) ─────────────────

# Verified from opencode.ai/go — August 31, 2026
PROMOTIONS: list[UsagePromotion] = [
    # GLM-5.3-Flash: 2× usage — English canonical banner + localized confirmation
    UsagePromotion(
        provider="opencode",
        plan="go",
        model_id="glm-5.3-flash",
        promotion_type="usage_limit_multiplier",
        multiplier=2.0,
        scope=["5h", "week", "month"],  # localized pages show all windows doubled
        evidence_id="opencode-go-glm-2x-aug2026",
        verification_state=VerificationState.RECONCILED.value,
    ),
    # Hy3: inconsistency between /docs/go/ (4,300) and /go (5,400)
    UsagePromotion(
        provider="opencode",
        plan="go",
        model_id="hy3",
        promotion_type="usage_limit_multiplier",
        multiplier=1.26,  # 5,400 / 4,300 = observed discrepancy
        scope=["5h"],
        evidence_id="opencode-go-hy3-inconsistency-aug2026",
        verification_state=VerificationState.CONFLICTING_SOURCES.value,
    ),
]


# ─── Pricing Concepts ────────────────────────────────────────────────────────

@dataclass
class PricingBundle:
    """All economic context for one model+provider combination."""
    list_input_per_1m: float | None = None
    list_output_per_1m: float | None = None
    list_cached_per_1m: float | None = None
    amortized_input_per_1m: float | None = None   # list / base_value_multiplier
    amortized_output_per_1m: float | None = None
    marginal_input_per_1m: float | None = None     # 0 if user has Go quota
    quota_cost_per_request: float | None = None     # consumes scarce Go quota
    subscription_multiplier: float = 1.0            # base_value_multiplier
    promotion_multiplier: float = 1.0
    effective_multiplier: float = 1.0               # base × promo
    subscription_fee_usd: float = 0.0
    model_usage_usd: float = 0.0


def compute_pricing(
    tariff: GoModelTariff | None,
    plan: GoPlan = GO_PLAN,
    promos: list[UsagePromotion] | None = None,
) -> PricingBundle:
    """Compute all pricing concepts for a model tariff.

    The amortized price is: list_price × (plan_fee / model_usage)
    NOT list_price / 6.

    Promotions are applied ON TOP of base subscription economics.
    Only promotions with scope including the target window are applied.
    """
    if tariff is None:
        return PricingBundle()

    # Base value multiplier: model's share of the subscription pool
    base_multiplier = tariff.model_usage_monthly_usd / plan.monthly_fee_usd

    # Promotion multiplier (from temporal facts, not base tariff)
    promo_mult = 1.0
    promo_state = VerificationState.CANDIDATE.value
    if promos:
        for p in promos:
            if p.model_id == tariff.model_id and p.promotion_type == "usage_limit_multiplier":
                # Only apply if scope includes month (full utilization)
                if "month" in p.scope or "unknown" in p.scope:
                    promo_mult *= p.multiplier
                    promo_state = p.verification_state

    effective_multiplier = base_multiplier * promo_mult

    return PricingBundle(
        list_input_per_1m=tariff.input_per_1m,
        list_output_per_1m=tariff.output_per_1m,
        list_cached_per_1m=tariff.cached_read_per_1m,
        amortized_input_per_1m=tariff.input_per_1m / effective_multiplier,
        amortized_output_per_1m=tariff.output_per_1m / effective_multiplier,
        marginal_input_per_1m=0.0,  # sunk cost if Go quota available
        subscription_multiplier=base_multiplier,
        promotion_multiplier=promo_mult,
        effective_multiplier=effective_multiplier,
        subscription_fee_usd=plan.monthly_fee_usd,
        model_usage_usd=tariff.model_usage_monthly_usd,
    )


# ─── Reconciliation Validator ────────────────────────────────────────────────

def request_cost_usd(tariff: GoModelTariff) -> float:
    """Cost of a typical request in USD."""
    return (
        tariff.typical_request.get("input", 0) * tariff.input_per_1m
        + tariff.typical_request.get("cached_read", 0) * tariff.cached_read_per_1m
        + tariff.typical_request.get("output", 0) * tariff.output_per_1m
    ) / 1_000_000


def allowance_for_window(plan: GoPlan, tariff: GoModelTariff, window: str) -> float:
    """Model's dollar allowance for a time window."""
    model_share = tariff.model_usage_monthly_usd / plan.limits["month"]
    return plan.limits.get(window, 0) * model_share


def expected_requests(plan: GoPlan, tariff: GoModelTariff, window: str) -> float:
    """Calculated request count for a window."""
    cost = request_cost_usd(tariff)
    if cost <= 0:
        return 0
    allowance = allowance_for_window(plan, tariff, window)
    return allowance / cost


def reconcile_tariff(
    plan: GoPlan, tariff: GoModelTariff, tolerance: float = 0.02
) -> dict:
    """Verify that our interpretation of OpenCode's economics reproduces
    their published request limits. Returns reconciliation results.

    A 2% tolerance is used because OpenCode's request counts are estimates.
    """
    results = {}
    for window, published in tariff.published_request_limits.items():
        calculated = expected_requests(plan, tariff, window)
        if published > 0:
            relative_error = abs(calculated - published) / published
        else:
            relative_error = float("inf")
        results[window] = {
            "calculated": round(calculated),
            "published": published,
            "relative_error_pct": round(relative_error * 100, 2),
            "reconciled": relative_error <= tolerance,
        }
    return results


def reconcile_all(plan: GoPlan = GO_PLAN) -> dict:
    """Reconcile all tariffs against published limits."""
    return {
        t.model_id: reconcile_tariff(plan, t)
        for t in GO_TARIFFS
        if t.published_request_limits
    }


# ─── ModelRoute (public interface) ───────────────────────────────────────────

@dataclass
class ModelRoute:
    """A single route to a model through a provider."""
    provider: str = ""
    model_id: str = ""
    input_per_1m: float | None = None
    output_per_1m: float | None = None
    cached_input_per_1m: float | None = None
    context_tokens: int | None = None
    quality_tier: str | None = None
    max_output_tokens: int | None = None
    modalities: str | list | None = None
    promotion: dict | None = None
    freshness: dict | None = None
    subscription_monthly_usd: float | None = None
    usage_value_usd_month: float | None = None

    @property
    def pricing(self) -> PricingBundle:
        """All pricing concepts for this route."""
        tariff = _TARIFF_MAP.get(self.model_id or "", None)
        if tariff is None and self.provider and self.model_id:
            # Try fuzzy match
            for tid, t in _TARIFF_MAP.items():
                if tid.replace("-", "").lower() == (self.model_id or "").replace("-", "").lower():
                    tariff = t
                    break
        promos = [p for p in PROMOTIONS if p.model_id == (self.model_id or "")]
        return compute_pricing(tariff, GO_PLAN, promos)

    @property
    def effective_input_per_1m(self) -> float | None:
        """Amortized input cost per 1M tokens.

        This is list_price / effective_multiplier.
        Use this for routing decisions — it reflects the true cost of
        a fully-utilized subscription, not the raw API price.
        """
        p = self.pricing
        return p.amortized_input_per_1m

    @property
    def effective_output_per_1m(self) -> float | None:
        """Amortized output cost per 1M tokens."""
        return self.pricing.amortized_output_per_1m

    @property
    def subscription_multiplier(self) -> float:
        """The effective multiplier (base × promo)."""
        return self.pricing.effective_multiplier


@dataclass
class MarketSnapshot:
    """Point-in-time view of available models and pricing."""
    models: dict[str, list[ModelRoute]] = field(default_factory=dict)
    fetched_at: float = 0.0
    source: str = ""  # "livellm", "cache", "hardcoded"

    @property
    def age_seconds(self) -> float:
        return time.time() - self.fetched_at if self.fetched_at else float("inf")


# ─── Hardcoded defaults (fallback when LiveLLM is unreachable) ───────────────

_DEFAULT_MODELS = {
    "MiMo V2.5": [
        ModelRoute(
            provider="OpenCode",
            model_id="mimo-v2.5",
            input_per_1m=0.14,
            output_per_1m=0.28,
            cached_input_per_1m=0.0028,
            context_tokens=1_000_000,
            max_output_tokens=32_768,
            modalities="text",
            subscription_monthly_usd=10,
            usage_value_usd_month=60,
        ),
    ],
    "GLM-5.3-Flash": [
        ModelRoute(
            provider="OpenCode",
            model_id="glm-5.3-flash",
            input_per_1m=0.15,
            output_per_1m=0.5,
            cached_input_per_1m=0.03,
            context_tokens=128_000,
            max_output_tokens=8_192,
            modalities="text",
            subscription_monthly_usd=10,
            usage_value_usd_month=15,
        ),
        ModelRoute(
            provider="Z.ai",
            model_id="glm-5.3-flash",
            input_per_1m=0.075,
            output_per_1m=0.25,
            cached_input_per_1m=0.015,
            context_tokens=128_000,
            modalities="text",
            promotion={"type": "price_discount", "discount_pct": 50},
        ),
    ],
    "DeepSeek V4 Flash": [
        ModelRoute(
            provider="OpenCode",
            model_id="deepseek-v4-flash",
            input_per_1m=0.22,
            output_per_1m=0.66,
            cached_input_per_1m=0.007,
            context_tokens=1_000_000,
            max_output_tokens=32_768,
            modalities="text",
            subscription_monthly_usd=10,
            usage_value_usd_month=30,
        ),
    ],
}


class MarketClient:
    """Fetches and caches model pricing data from LiveLLM."""

    CACHE_PATH = Path("/root/mwgym/data/market-cache.json")
    REFRESH_INTERVAL_S = 300  # 5 minutes

    def __init__(self, base_url: str = "", cache_path: Path | str = ""):
        self.base_url = base_url or os.environ.get("LIVELLM_URL", "http://127.0.0.1:3847")
        self.cache_path = Path(cache_path) if cache_path else self.CACHE_PATH
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._snapshot: MarketSnapshot | None = None
        self._last_fetch: float = 0.0

    def fetch(self, force: bool = False) -> MarketSnapshot | None:
        """Fetch market data from LiveLLM, with cache fallback."""
        now = time.time()
        if not force and self._snapshot and (now - self._last_fetch) < self.REFRESH_INTERVAL_S:
            return self._snapshot

        snap = self._fetch_live()
        if snap:
            self._snapshot = snap
            self._last_fetch = now
            self._save_cache(snap)
            return snap

        snap = self._load_cache()
        if snap:
            self._snapshot = snap
            self._last_fetch = now
            return snap

        snap = MarketSnapshot(
            models=_DEFAULT_MODELS,
            fetched_at=time.time(),
            source="hardcoded",
        )
        self._snapshot = snap
        self._last_fetch = now
        return snap

    def _fetch_live(self) -> MarketSnapshot | None:
        """Fetch from LiveLLM API."""
        import http.client
        from urllib.parse import urlparse

        parsed = urlparse(self.base_url)
        try:
            if parsed.scheme == "https":
                import ssl
                ctx = ssl.create_default_context()
                conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, context=ctx, timeout=5)
            else:
                conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)

            conn.request("GET", "/v1/market")
            resp = conn.getresponse()
            body = resp.read().decode()
            if resp.status != 200:
                return None

            data = json.loads(body)
            snap = MarketSnapshot(
                fetched_at=time.time(),
                source="livellm",
            )

            for m in data.get("models", []):
                name = m.get("model", "unknown")
                routes = []
                for r in m.get("routes", []):
                    routes.append(ModelRoute(
                        provider=r.get("provider", ""),
                        model_id=r.get("model_id", name.lower().replace(" ", "-")),
                        input_per_1m=r.get("input"),
                        output_per_1m=r.get("output"),
                        cached_input_per_1m=r.get("cached_input"),
                        context_tokens=r.get("context_tokens"),
                        quality_tier=r.get("quality_tier"),
                        max_output_tokens=r.get("max_output_tokens"),
                        modalities=r.get("modalities"),
                        promotion=r.get("promotion"),
                        freshness=r.get("freshness"),
                        subscription_monthly_usd=r.get("monthly"),
                        usage_value_usd_month=r.get("usage_value_usd_month"),
                    ))
                snap.models[name] = routes

            return snap

        except Exception:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _load_cache(self) -> MarketSnapshot | None:
        if not self.cache_path.exists():
            return None
        try:
            data = json.loads(self.cache_path.read_text())
            models = {}
            for name, routes in data.get("models", {}).items():
                models[name] = [ModelRoute(**r) for r in routes]
            return MarketSnapshot(
                models=models,
                fetched_at=data.get("fetched_at", 0),
                source=data.get("source", "cache"),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def _save_cache(self, snap: MarketSnapshot):
        data = {
            "fetched_at": snap.fetched_at,
            "source": snap.source,
            "models": {}
        }
        for name, routes in snap.models.items():
            data["models"][name] = [
                {k: v for k, v in r.__dict__.items() if v is not None}
                for r in routes
            ]
        self.cache_path.write_text(json.dumps(data, indent=2))
