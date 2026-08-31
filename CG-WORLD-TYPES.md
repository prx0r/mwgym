# CG World Types — Mapped from Oracle Data

## The Key Insight from Oracle

> "Moltwork should search for economic objective functions, not merely jobs."

30 ranked markets, 18 skill families, 9 program types.

The question: **what CG worldpack do we need for each?**

## CG World Categories

### World Type 1: API ENDPOINT (F1)
**Markets:** x402 Bazaar, x402 Arena, req402, tools402, Agent Wonderland
**What agent does:** Define schema → implement handler → deploy → monitor
**Verifier:** endpoint responds, schema valid, latency acceptable
**Feedback loop:** seconds

**CG Worldpack:**
```
worlds/
  api_endpoint/
    manifest.json
    world.py          # HTTP server + test client
    policies.py       # which framework, which auth
    experience.py     # track cost/quality/latency
    verifier.py       # curl endpoint, check response
    scenarios/
      simple_crud.yaml
      streaming.yaml
      authenticated.yaml
      paid_x402.yaml
```

### World Type 2: BROWSER EXTENSION (F2)
**Markets:** Chrome Web Store, Firefox Add-ons, Edge Add-ons
**What agent does:** manifest → popup → content script → test → publish
**Verifier:** manifest valid, content script runs, screenshots match
**Feedback loop:** minutes

**CG Worldpack:**
```
worlds/
  browser_extension/
    world.py          # Playwright test harness
    verifier.py       # manifest check, DOM test, screenshot compare
    scenarios/
      content_script.yaml
      popup_ui.yaml
      cross_browser.yaml
```

### World Type 3: SAAS INTEGRATION (F3)
**Markets:** Atlassian Forge, HubSpot, Salesforce, Zendesk, 20+ platforms
**What agent does:** OAuth → API integration → test → marketplace listing
**Verifier:** OAuth completes, API calls succeed, UI renders
**Feedback loop:** minutes-hours

**CG Worldpack:**
```
worlds/
  saas_integration/
    world.py          # OAuth flow + API sandbox
    verifier.py       # token valid, CRUD works, listing valid
    scenarios/
      forge_jira.yaml
      hubspot_crm.yaml
      salesforce_app.yaml
```

### World Type 4: GAME DEV (F5/F6)
**Markets:** Roblox, Fortnite UEFN, Unity Asset Store
**What agent does:** Write game code → test → publish
**Verifier:** code compiles, game runs, no errors
**Feedback loop:** minutes-hours

**CG Worldpack:**
```
worlds/
  game_dev/
    world.py          # Game engine test harness
    verifier.py       # compile check, run test, screenshot
    scenarios/
      roblox_mechanic.yaml
      fortnite_verse.yaml
      unity_asset.yaml
```

### World Type 5: RESEARCH/ML (F8-F10)
**Markets:** Kaggle, Metaculus, Numerai, DrivenData, ARC Prize
**What agent does:** Analyze data → build model → evaluate → submit
**Verifier:** metric threshold, submission format valid
**Feedback loop:** hours-days

**CG Worldpack:**
```
worlds/
  research_ml/
    world.py          # Data loading + model training + eval
    verifier.py       # metric check, submission format
    scenarios/
      kaggle_sim.yaml
      metaculus_forecast.yaml
      numerai_model.yaml
```

### World Type 6: SECURITY/BOUNTY (F11)
**Markets:** Immunefi, Cantina, HackerOne, Bugcrowd
**What agent does:** Audit code → find vulnerability → write report → submit
**Verifier:** vulnerability exists, report valid, fix works
**Feedback loop:** hours-days

**CG Worldpack:**
```
worlds/
  security_bounty/
    world.py          # Code audit + vulnerability scanner
    verifier.py       # vulnerability exists, fix works
    scenarios/
      smart_contract.yaml
      api_endpoint.yaml
      web_app.yaml
```

### World Type 7: CONTENT/CREATOR (F12-F14)
**Markets:** CurseForge, Modrinth, Canva, Webflow, Framer
**What agent does:** Create asset → test quality → publish → track usage
**Verifier:** asset valid, no errors, marketplace listing works
**Feedback loop:** days-weeks

**CG Worldpack:**
```
worlds/
  creator_content/
    world.py          # Asset creation + quality check
    verifier.py       # format valid, quality threshold
    scenarios/
      curseforge_mod.yaml
      canva_template.yaml
      webflow_template.yaml
```

## Priority Order (from Oracle rankings)

| Priority | World Type | Markets | Revenue Potential |
|----------|-----------|---------|-------------------|
| 1 | API Endpoint | x402 ecosystem | High (recurring) |
| 2 | Research/ML | Kaggle, Metaculus, Numerai | High (prizes) |
| 3 | SaaS Integration | 20+ platforms | High (recurring) |
| 4 | Browser Extension | Chrome/Firefox | Medium |
| 5 | Security Bounty | Immunefi, Cantina | High (bounties) |
| 6 | Game Dev | Roblox, Fortnite | Medium |
| 7 | Content/Creator | CurseForge, Canva | Medium |

## What CG Already Has

CG's `toy.signal_game` world is a simple proof of concept.
We need to build World Type 1 (API Endpoint) first because:

1. **Fastest feedback loop** — seconds, not hours
2. **Most markets** — 15+ markets use API endpoints
3. **Easiest to verify** — curl endpoint, check response
4. **Highest reusability** — one skill serves many markets

## The Plan

1. Build `api_endpoint` worldpack (CG format)
2. Create 10 API endpoint tasks (from Oracle data)
3. Run evolution campaign with CGE1
4. Track results with CG event sourcing
5. Sell winning configs as git assets

This is the path from Oracle intelligence → CG worlds → sellable assets.
