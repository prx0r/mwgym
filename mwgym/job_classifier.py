"""Job Classifier — maps Oracle job offers to CG world types.

Classification is PROCESS-based, not market-based.
Two jobs from the same market can need different worlds.

The classifier asks: "What does the agent literally do, step by step?"
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ClassificationResult:
    world_type: str
    skill_family: str
    confidence: float
    reasoning: str


# Process patterns → world type
PROCESS_RULES = [
    # F1: API Endpoint
    {
        "world_type": "api_endpoint",
        "skill_family": "F1",
        "patterns": [
            r"api\s*endpoint", r"http\s*handler", r"rest\s*api",
            r"webhook", r"micro.?service", r"x402", r"pay.*endpoint",
            r"deploy.*api", r"schema.*valid",
        ],
        "tools_hint": ["http", "api", "endpoint", "deploy", "curl"],
    },
    # F2: Browser Extension
    {
        "world_type": "browser_extension",
        "skill_family": "F2",
        "patterns": [
            r"chrome\s*extension", r"firefox\s*addon", r"browser\s*extension",
            r"manifest\.json", r"content\s*script", r"popup", r"dom\s*inject",
        ],
        "tools_hint": ["playwright", "chrome", "manifest", "browser"],
    },
    # F3: SaaS Integration
    {
        "world_type": "saas_integration",
        "skill_family": "F3",
        "patterns": [
            r"oauth", r"saas", r"integration", r"crm", r"jira",
            r"hubspot", r"salesforce", r"zendesk", r"forge",
            r"marketplace\s*listing", r"app\s*store",
        ],
        "tools_hint": ["oauth", "api", "webhook", "ui"],
    },
    # F4: E-commerce
    {
        "world_type": "ecommerce",
        "skill_family": "F4",
        "patterns": [
            r"shopify", r"woocommerce", r"ecommerce", r"checkout",
            r"product\s*sync", r"order\s*process", r"payment",
        ],
        "tools_hint": ["shopify", "checkout", "payment", "inventory"],
    },
    # F5: Game Dev (Roblox)
    {
        "world_type": "game_dev",
        "skill_family": "F5",
        "patterns": [
            r"roblox", r"luau", r"studio", r"game\s*mode",
            r"obby", r"multiplayer", r"place.*publish",
        ],
        "tools_hint": ["roblox", "luau", "studio"],
    },
    # F6: Game Dev (Fortnite/UEFN)
    {
        "world_type": "game_dev",
        "skill_family": "F6",
        "patterns": [
            r"fortnite", r"uefn", r"verse", r"unreal",
            r"creator\s*portal", r"island",
        ],
        "tools_hint": ["uefn", "verse", "unreal"],
    },
    # F8: Web Scraping
    {
        "world_type": "web_scraping",
        "skill_family": "F8",
        "patterns": [
            r"scrape", r"crawl", r"extract.*data", r"parser",
            r"anti.?bot", r"headless\s*browser", r"normalize",
        ],
        "tools_hint": ["scraper", "parser", "browser", "proxy"],
    },
    # F9: Research/Analysis
    {
        "world_type": "research_analysis",
        "skill_family": "F9",
        "patterns": [
            r"research", r"analysis", r"forecast", r"predict",
            r"synthesis", r"report", r"literature\s*review",
            r"metaculus", r"kaggle", r"numerai",
        ],
        "tools_hint": ["search", "analysis", "report", "data"],
    },
    # F10: Security Audit
    {
        "world_type": "security_audit",
        "skill_family": "F10",
        "patterns": [
            r"security\s*audit", r"vulnerability", r"bug\s*bounty",
            r"penetration", r"smart\s*contract.*audit", r"immunefi",
        ],
        "tools_hint": ["audit", "scanner", "security"],
    },
    # F11: Content Creation
    {
        "world_type": "content_creation",
        "skill_family": "F11",
        "patterns": [
            r"template", r"design", r"ui.*design", r"graphic",
            r"canva", r"webflow", r"framer", r"figma",
        ],
        "tools_hint": ["design", "template", "ui", "figma"],
    },
    # F12: ML/Model Training
    {
        "world_type": "ml_training",
        "skill_family": "F12",
        "patterns": [
            r"train.*model", r"ml\s*model", r"neural\s*network",
            r"pytorch", r"tensorflow", r"huggingface", r"fine.?tun",
        ],
        "tools_hint": ["model", "train", "dataset", "eval"],
    },
    # F13: Documentation
    {
        "world_type": "documentation",
        "skill_family": "F13",
        "patterns": [
            r"documentation", r"readme", r"api\s*doc", r"tutorial",
            r"guide", r"onboarding",
        ],
        "tools_hint": ["markdown", "docs", "tutorial"],
    },
]


def classify_job(title: str, description: str = "", tags: list[str] = None) -> ClassificationResult:
    """Classify a job offer into a CG world type.

    Classification is process-based: what does the agent literally do?
    """
    text = f"{title} {description} {' '.join(tags or [])}".lower()

    best_match = None
    best_score = 0

    for rule in PROCESS_RULES:
        score = 0
        for pattern in rule["patterns"]:
            if re.search(pattern, text):
                score += 1

        # Bonus for tool hints
        for hint in rule.get("tools_hint", []):
            if hint in text:
                score += 0.5

        if score > best_score:
            best_score = score
            best_match = rule

    if best_match and best_score > 0:
        return ClassificationResult(
            world_type=best_match["world_type"],
            skill_family=best_match["skill_family"],
            confidence=min(1.0, best_score / 3),  # normalize to [0, 1]
            reasoning=f"Matched {best_score} patterns for {best_match['skill_family']}",
        )

    # Default: generic coding task
    return ClassificationResult(
        world_type="generic_coding",
        skill_family="F0",
        confidence=0.3,
        reasoning="No specific process pattern matched",
    )


def classify_from_oracle(market: str, program_type: str = "") -> ClassificationResult:
    """Classify based on Oracle market data."""
    market_lower = market.lower()

    # Direct market mappings
    MARKET_MAP = {
        "metaculus": ("research_analysis", "F9", 0.9),
        "kaggle": ("ml_training", "F12", 0.9),
        "numerai": ("ml_training", "F12", 0.9),
        "allora": ("research_analysis", "F9", 0.8),
        "roblox": ("game_dev", "F5", 0.9),
        "fortnite": ("game_dev", "F6", 0.9),
        "curseforge": ("game_dev", "F5", 0.8),
        "modrinth": ("game_dev", "F5", 0.8),
        "shopify": ("ecommerce", "F4", 0.9),
        "chrome": ("browser_extension", "F2", 0.9),
        "immunefi": ("security_audit", "F10", 0.9),
        "cantina": ("security_audit", "F10", 0.9),
        "x402": ("api_endpoint", "F1", 0.9),
        "canva": ("content_creation", "F11", 0.8),
        "webflow": ("content_creation", "F11", 0.8),
        "framer": ("content_creation", "F11", 0.8),
    }

    for key, (world, family, conf) in MARKET_MAP.items():
        if key in market_lower:
            return ClassificationResult(
                world_type=world,
                skill_family=family,
                confidence=conf,
                reasoning=f"Direct market match: {key}",
            )

    # Program type mappings
    PROGRAM_MAP = {
        "monetized_scoreboard": ("research_analysis", "F9", 0.8),
        "prize_market": ("ml_training", "F12", 0.8),
        "creator_royalty": ("content_creation", "F11", 0.7),
        "platform_subsidy": ("game_dev", "F5", 0.7),
        "protocol_machine_work": ("api_endpoint", "F1", 0.8),
        "paid_verification": ("security_audit", "F10", 0.8),
        "job_market": ("generic_coding", "F0", 0.5),
    }

    for key, (world, family, conf) in PROGRAM_MAP.items():
        if key in (program_type or "").lower():
            return ClassificationResult(
                world_type=world,
                skill_family=family,
                confidence=conf,
                reasoning=f"Program type match: {key}",
            )

    return ClassificationResult(
        world_type="generic_coding",
        skill_family="F0",
        confidence=0.3,
        reasoning="No specific match found",
    )


if __name__ == "__main__":
    # Test classification
    tests = [
        ("Build a Chrome extension that extracts prices", "", ["browser"]),
        ("Write a Roblox obby game", "", ["roblox", "game"]),
        ("Create a Shopify app for inventory sync", "", ["shopify", "ecommerce"]),
        ("Audit this smart contract for vulnerabilities", "", ["security", "audit"]),
        ("Train a model for Kaggle competition", "", ["kaggle", "ml"]),
        ("Build an x402 payment endpoint", "", ["x402", "api"]),
        ("Write documentation for this API", "", ["docs", "api"]),
    ]

    for title, desc, tags in tests:
        result = classify_job(title, desc, tags)
        print(f"{title[:50]:50} → {result.world_type} ({result.skill_family}, {result.confidence:.2f})")
