"""Job Classifier — maps Oracle job offers to CG world types.

Two dimensions:
1. PROCESS TYPE: What does the agent literally do? (determines CG world)
2. AUTONOMY LEVEL: How much can the agent do alone? (H0-H4)

Same process type, different autonomy = same CG world, different config.

Example:
- Roblox game = Game Dev + H0 (publish via REST)
- Fortnite game = Game Dev + H1 (publish needs human)
- Unity asset = Game Dev + H2 (asset store review)

All three use the same GameDevWorld, but with different autonomy configs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ClassificationResult:
    process_type: str    # What the agent does
    autonomy_level: str  # How much it can do alone (H0-H4)
    cg_world: str        # Which CG worldpack to use
    confidence: float
    reasoning: str


# Process types → CG worlds
# Autonomy levels are orthogonal, determined by market constraints
PROCESS_TYPES = {
    "api_endpoint": {
        "cg_world": "api_endpoint",
        "patterns": [
            r"api\s*endpoint", r"http\s*handler", r"rest\s*api",
            r"webhook", r"micro.?service", r"x402", r"pay.*endpoint",
            r"deploy.*api", r"schema.*valid",
        ],
        "tools_hint": ["http", "api", "endpoint", "deploy", "curl"],
    },
    "browser_extension": {
        "cg_world": "browser_extension",
        "patterns": [
            r"chrome\s*extension", r"firefox\s*addon", r"browser\s*extension",
            r"manifest\.json", r"content\s*script", r"popup", r"dom\s*inject",
        ],
        "tools_hint": ["playwright", "chrome", "manifest", "browser"],
    },
    "platform_integration": {
        "cg_world": "platform_integration",
        "patterns": [
            r"oauth", r"saas", r"integration", r"crm", r"jira",
            r"hubspot", r"salesforce", r"zendesk", r"forge",
            r"marketplace\s*listing", r"app\s*store",
            r"shopify", r"woocommerce", r"ecommerce", r"checkout",
            r"product\s*sync", r"order\s*process", r"payment",
        ],
        "tools_hint": ["oauth", "api", "webhook", "ui", "shopify", "checkout"],
    },
    "game_dev": {
        "cg_world": "game_dev",
        "patterns": [
            r"roblox", r"luau", r"studio", r"game\s*mode",
            r"obby", r"multiplayer", r"place.*publish",
            r"fortnite", r"uefn", r"verse", r"unreal",
            r"creator\s*portal", r"island",
            r"unity", r"unreal\s*engine", r"c#\s*script",
            r"asset\s*store", r"game\s*asset",
        ],
        "tools_hint": ["roblox", "luau", "studio", "uefn", "verse", "unreal", "unity"],
    },
    "web_scraping": {
        "cg_world": "web_scraping",
        "patterns": [
            r"scrape", r"crawl", r"extract.*data", r"parser",
            r"anti.?bot", r"headless\s*browser", r"normalize",
        ],
        "tools_hint": ["scraper", "parser", "browser", "proxy"],
    },
    "research_analysis": {
        "cg_world": "research_analysis",
        "patterns": [
            r"research", r"analysis", r"forecast", r"predict",
            r"synthesis", r"report", r"literature\s*review",
            r"metaculus", r"kaggle", r"numerai",
        ],
        "tools_hint": ["search", "analysis", "report", "data"],
    },
    "security_audit": {
        "cg_world": "security_audit",
        "patterns": [
            r"security\s*audit", r"vulnerability", r"bug\s*bounty",
            r"penetration", r"smart\s*contract.*audit", r"immunefi",
        ],
        "tools_hint": ["audit", "scanner", "security"],
    },
    "content_creation": {
        "cg_world": "content_creation",
        "patterns": [
            r"template", r"design", r"ui.*design", r"graphic",
            r"canva", r"webflow", r"framer", r"figma",
        ],
        "tools_hint": ["design", "template", "ui", "figma"],
    },
    "ml_training": {
        "cg_world": "ml_training",
        "patterns": [
            r"train.*model", r"ml\s*model", r"neural\s*network",
            r"pytorch", r"tensorflow", r"huggingface", r"fine.?tun",
        ],
        "tools_hint": ["model", "train", "dataset", "eval"],
    },
    "documentation": {
        "cg_world": "documentation",
        "patterns": [
            r"documentation", r"readme", r"api\s*doc", r"tutorial",
            r"guide", r"onboarding",
        ],
        "tools_hint": ["markdown", "docs", "tutorial"],
    },
}

# Autonomy level detection
# H0: Fully autonomous (can complete without human)
# H1: Mostly autonomous (needs human for review/approval only)
# H2: Partially autonomous (needs human for critical steps like publishing)
# H3: Assisted (human does most work, agent assists)
# H4: Human-only (agent can't do this)

AUTONOMY_PATTERNS = {
    "H0": [
        r"api.*endpoint", r"webhook", r"scrape", r"extract",
        r"metaculus.*bot", r"kaggle.*submit", r"numerai",
        r"x402.*endpoint", r"automated", r"self.?service",
    ],
    "H1": [
        r"review", r"approval", r"listing", r"publish.*review",
        r"marketplace.*submit", r"app.*store.*review",
        r"template.*royalty", r"mod.*upload",
    ],
    "H2": [
        r"creator\s*portal", r"human.*publish", r"manual.*submit",
        r"asset.*store.*review", r"security.*report.*submit",
        r"bounty.*submit", r"competition.*submit",
    ],
    "H3": [
        r"collaborate", r"assist", r"pair.*program", r"review.*together",
    ],
}

# Market-specific autonomy overrides
MARKET_AUTONOMY = {
    "roblox": "H0",      # Studio MCP → REST publish (full auto)
    "fortnite": "H1",    # Creator Portal requires human
    "unity": "H2",       # Asset store review
    "unreal": "H2",      # Marketplace review
    "chrome": "H0",      # Web Store API (auto publish)
    "firefox": "H0",     # Add-ons API (auto publish)
    "shopify": "H1",     # App store review
    "x402": "H0",        # Protocol-native (auto)
    "metaculus": "H0",   # Bot API (auto)
    "kaggle": "H0",      # Submit API (auto)
    "numerai": "H0",     # Stake API (auto)
    "immunefi": "H2",    # Report submission
    "cantina": "H2",     # Report submission
    "curseforge": "H1",  # Upload + review
    "modrinth": "H1",    # Upload + review
    "canva": "H1",       # Template review
    "webflow": "H1",     # Template listing
}


def classify_job(title: str, description: str = "", tags: list[str] = None) -> ClassificationResult:
    """Classify a job offer into CG world type × autonomy level."""
    text = f"{title} {description} {' '.join(tags or [])}".lower()

    # Classify process type
    best_process = None
    best_score = 0

    for proc_type, rule in PROCESS_TYPES.items():
        score = 0
        for pattern in rule["patterns"]:
            if re.search(pattern, text):
                score += 1
        for hint in rule.get("tools_hint", []):
            if hint in text:
                score += 0.5
        if score > best_score:
            best_score = score
            best_process = proc_type

    if not best_process or best_score == 0:
        return ClassificationResult(
            process_type="generic_coding",
            autonomy_level="H0",
            cg_world="generic_coding",
            confidence=0.3,
            reasoning="No specific process pattern matched",
        )

    # Detect autonomy level (market-specific overrides first)
    autonomy = _detect_autonomy(text)

    cg_world = PROCESS_TYPES[best_process]["cg_world"]
    confidence = min(1.0, best_score / 3)

    return ClassificationResult(
        process_type=best_process,
        autonomy_level=autonomy,
        cg_world=cg_world,
        confidence=confidence,
        reasoning=f"{best_process} + {autonomy} (score={best_score:.1f})",
    )


def _detect_autonomy(text: str) -> str:
    """Detect autonomy level. Market-specific overrides take priority."""
    # Check market-specific overrides first
    for market, level in MARKET_AUTONOMY.items():
        if market in text:
            return level

    # Check explicit H-level mentions
    for level in ["H4", "H3", "H2", "H1", "H0"]:
        if f" {level} " in text or text.startswith(level):
            return level

    # Check patterns
    for level in ["H0", "H1", "H2", "H3"]:
        for pattern in AUTONOMY_PATTERNS.get(level, []):
            if re.search(pattern, text):
                return level

    # Default: H1
    return "H1"


def classify_from_oracle(market: str, program_type: str = "") -> ClassificationResult:
    """Classify based on Oracle market data."""
    market_lower = market.lower()

    # Market → process type + autonomy
    MARKET_MAP = {
        "metaculus": ("research_analysis", "H0"),
        "kaggle": ("ml_training", "H0"),
        "numerai": ("ml_training", "H0"),
        "allora": ("research_analysis", "H0"),
        "roblox": ("game_dev", "H0"),
        "fortnite": ("game_dev", "H1"),
        "unity": ("game_dev", "H2"),
        "unreal": ("game_dev", "H2"),
        "curseforge": ("game_dev", "H1"),
        "modrinth": ("game_dev", "H1"),
        "shopify": ("platform_integration", "H1"),
        "chrome": ("browser_extension", "H0"),
        "firefox": ("browser_extension", "H0"),
        "immunefi": ("security_audit", "H2"),
        "cantina": ("security_audit", "H2"),
        "x402": ("api_endpoint", "H0"),
        "canva": ("content_creation", "H1"),
        "webflow": ("content_creation", "H1"),
        "framer": ("content_creation", "H1"),
    }

    for key, (proc_type, autonomy) in MARKET_MAP.items():
        if key in market_lower:
            cg_world = PROCESS_TYPES.get(proc_type, {}).get("cg_world", "generic_coding")
            return ClassificationResult(
                process_type=proc_type,
                autonomy_level=autonomy,
                cg_world=cg_world,
                confidence=0.9,
                reasoning=f"Market match: {key} → {proc_type} + {autonomy}",
            )

    return ClassificationResult(
        process_type="generic_coding",
        autonomy_level="H1",
        cg_world="generic_coding",
        confidence=0.3,
        reasoning="No specific market match",
    )


if __name__ == "__main__":
    tests = [
        ("Build a Chrome extension", "", ["chrome"]),
        ("Write a Roblox obby game", "", ["roblox"]),
        ("Create a Fortnite UEFN island", "", ["fortnite"]),
        ("Create a Shopify app", "", ["shopify"]),
        ("Audit smart contract", "", ["security"]),
        ("Train Kaggle model", "", ["kaggle"]),
        ("Build x402 endpoint", "", ["x402"]),
        ("Write API docs", "", ["docs"]),
        ("Metaculus forecasting bot", "", ["metaculus"]),
        ("Scrape e-commerce prices", "", ["scrape"]),
    ]

    print(f"{'Job':55} {'Process':25} {'Auto':5} {'CG World':25}")
    print("-" * 115)
    for title, desc, tags in tests:
        r = classify_job(title, desc, tags)
        print(f"{title[:55]:55} {r.process_type:25} {r.autonomy_level:5} {r.cg_world:25}")
