"""Job Classifier — maps Oracle job offers to CG world types + marketplace adapters.

Three dimensions:
1. PROCESS TYPE: What does the agent literally do? (determines CG world)
2. AUTONOMY LEVEL: How much can the agent do alone? (H0-H4)
3. SKILL FAMILY: Which reusable skill does this exercise? (F0-F18)

Same process type, different autonomy = same CG world, different config.

Example:
- Roblox game = game_dev + H0 (publish via REST) → skill F5
- Fortnite game = game_dev + H1 (publish needs human) → skill F6
- Unity asset = game_dev + H2 (asset store review) → skill F7

All three use the same GameDevWorld, but with different autonomy configs.

The classifier also knows which marketplace adapters can handle each process type,
so the orchestrator can route jobs to the right submission channel.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ClassificationResult:
    process_type: str    # What the agent does
    skill_family: str    # Reusable skill (F0-F18)
    autonomy_level: str  # How much it can do alone (H0-H4)
    cg_world: str        # Which CG worldpack to use
    confidence: float
    reasoning: str
    recommended_adapters: list[str] = field(default_factory=list)  # marketplace IDs
    recommended_tools: list[str] = field(default_factory=list)     # MCP tools needed


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
    # F7: General game dev (Unity/Unreal assets, not Roblox/Fortnite specific)
    "game_asset": {
        "cg_world": "game_asset",
        "patterns": [
            r"asset\s*store", r"3d\s*model", r"shader", r"vfx",
            r"game\s*asset", r"unity\s*asset", r"unreal\s*asset",
            r"prefab", r"material", r"animation",
        ],
        "tools_hint": ["blender", "unity", "unreal", "asset"],
    },
    # F14: 3D/Creative assets
    "creative_3d": {
        "cg_world": "creative_3d",
        "patterns": [
            r"3d\s*(model|asset|print)", r"mesh", r"texture", r"uv\s*unwrap",
            r"render", r"blender", r"fab", r"turbosquid", r"cgtrader",
            r"stl", r"obj", r"fbx", r"low.?poly", r"lod",
        ],
        "tools_hint": ["blender", "3d", "mesh", "texture", "render"],
    },
    # F15: Scientific ML (different from generic ml_training)
    "scientific_ml": {
        "cg_world": "scientific_ml",
        "patterns": [
            r"medical\s*(imaging|data)", r"segmentation", r"dicom",
            r"ct\s*scan", r"mri", r"vesuvius", r"scroll",
            r"drivendata", r"grand\s*challenge", r"scientific.*benchmark",
            r"bioimaging", r"pathology",
        ],
        "tools_hint": ["medical", "imaging", "scientific", "benchmark"],
    },
    # F16: HR/CRM integration
    "hr_crm": {
        "cg_world": "hr_crm",
        "patterns": [
            r"hr\s*(system|integration|data)", r"bamboo", r"personio",
            r"greenhouse", r"lever", r"recruiting", r"applicant",
            r"employee\s*(sync|data)", r"payroll", r"crm\s*sync",
        ],
        "tools_hint": ["hr", "crm", "recruiting", "employee"],
    },
    # F17: Finance/accounting
    "finance_accounting": {
        "cg_world": "finance_accounting",
        "patterns": [
            r"accounting", r"ledger", r"invoic", r"reconcil",
            r"xero", r"quickbooks", r"sage", r"tax\s*export",
            r"financial\s*(report|data)", r"bookkeep",
        ],
        "tools_hint": ["accounting", "ledger", "invoice", "finance"],
    },
    # F18: Marketplace distribution (meta-skill)
    "distribution": {
        "cg_world": "distribution",
        "patterns": [
            r"cross.?list", r"app\s*store\s*optimization", r"aso",
            r"listing\s*optimi", r"marketplace\s*distribut",
            r"review\s*monitor", r"pricing\s*optimi",
        ],
        "tools_hint": ["listing", "distribution", "optimization"],
    },
    # Workflow automation (n8n, Make, Zapier)
    "workflow_automation": {
        "cg_world": "workflow_automation",
        "patterns": [
            r"n8n", r"zapier", r"make\.com", r"automat.*workflow",
            r"trigger.*action", r"pipeline", r"etl",
            r"webhook.*chain", r"error.*handl.*retry",
        ],
        "tools_hint": ["n8n", "zapier", "make", "workflow"],
    },
}

# Process type → skill family mapping
PROCESS_TO_SKILL = {
    "api_endpoint": "F1",
    "browser_extension": "F2",
    "platform_integration": "F3",
    "game_dev": "F5",       # Roblox/Fortnite specific
    "game_asset": "F7",     # Unity/Unreal general
    "web_scraping": "F8",
    "research_analysis": "F9",
    "security_audit": "F10",
    "content_creation": "F11",  # templates/themes
    "ml_training": "F12",
    "documentation": "F13",
    "creative_3d": "F14",
    "scientific_ml": "F15",
    "hr_crm": "F16",
    "finance_accounting": "F17",
    "distribution": "F18",
    "workflow_automation": "F19",
    "generic_coding": "F0",
}

# Process type → which marketplace adapters can handle it
PROCESS_TO_ADAPTERS = {
    "api_endpoint": ["x402arena", "req402", "agentpact", "dealwork", "olas"],
    "browser_extension": ["chromewebstore", "firefoxaddons", "edgeaddons"],
    "platform_integration": ["atlassian", "hubspot", "shopify", "monday",
                             "activecampaign", "asana", "salesforce"],
    "game_dev": ["roblox", "fortnite", "curseforge", "modrinth"],
    "game_asset": ["unity", "unreal", "fab", "itchio"],
    "web_scraping": ["apify", "agentdatahub"],
    "research_analysis": ["metaculus", "allora", "agentpact", "dealwork",
                          "toku", "drivendata", "aicrowd"],
    "security_audit": ["google_oss", "immunefi", "cantina", "hackenproof"],
    "content_creation": ["framer", "webflow", "canva", "creativemarket"],
    "ml_training": ["kaggle", "numerai", "drivendata", "aicrowd", "huggingface"],
    "documentation": ["github"],
    "creative_3d": ["fab", "turbosquid", "cgtrader", "renderhub"],
    "scientific_ml": ["drivendata", "aicrowd", "grandchallenge", "vesuvius"],
    "hr_crm": ["bambohr", "personio", "greenhouse", "lever", "salesforce"],
    "finance_accounting": ["xero", "quickbooks", "sage", "freshbooks", "visma"],
    "distribution": ["all"],  # meta-skill, applies everywhere
    "workflow_automation": ["n8n", "zapier", "make"],
    "generic_coding": ["agentpact", "dealwork", "moltjobs", "github"],
}

# Process type → MCP tools the agent needs
PROCESS_TO_TOOLS = {
    "api_endpoint": ["http_client", "schema_validator", "deploy_tool"],
    "browser_extension": ["playwright", "chrome_devtools", "screenshot"],
    "platform_integration": ["oauth_client", "api_client", "webhook_handler"],
    "game_dev": ["studio_mcp", "playwright", "rest_client"],
    "game_asset": ["blender_api", "editor_api", "screenshot"],
    "web_scraping": ["http_client", "html_parser", "playwright"],
    "research_analysis": ["web_search", "document_parser", "report_generator"],
    "security_audit": ["git_client", "compiler", "test_runner", "fuzzer"],
    "content_creation": ["design_tool", "screenshot", "responsive_tester"],
    "ml_training": ["python_runner", "gpu_access", "dataset_loader"],
    "documentation": ["markdown_editor", "screenshot"],
    "creative_3d": ["blender_api", "render_engine", "lod_optimizer"],
    "scientific_ml": ["python_runner", "gpu_access", "medical_reader"],
    "hr_crm": ["oauth_client", "api_client", "data_mapper"],
    "finance_accounting": ["oauth_client", "api_client", "reconciler"],
    "distribution": ["marketplace_api", "aso_tool", "review_monitor"],
    "workflow_automation": ["n8n_client", "webhook_handler", "error_monitor"],
    "generic_coding": ["git_client", "compiler", "test_runner"],
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
