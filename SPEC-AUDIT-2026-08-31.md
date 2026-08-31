# MWGym Spec Compliance Audit — 2026-08-31

## What the spec says vs what we built

### 1. BATS (Budget-Aware Token Scheduler)

**Spec says** (MWGYM-SPEC §11):
> YGO keeps simulator local. Inner loop: fast policy (no LLM). BATS decides when to invoke Letta/Hydra/strong model.

**WorkerKit has** (`providers/bats.py`):
- `BudgetState` — tracks spent/remaining USD, tokens, model calls
- `BATS.select_model()` — picks model based on task, budget, uncertainty
- `BATS.should_escalate()` — decides if quality needs a stronger model
- `BATS.should_branch()` — decides if we should explore candidates
- `BATS.should_verify()` — decides if we should verify the result

**MWGym has**: NOTHING using BATS. The YGO genome strategies just score actions with hardcoded thresholds. The router uses regex patterns, not BATS.

**Gap**: CRITICAL. BATS is the L0 reasoning allocator. YGO should use BATS to decide when to "buy expert hint" (synthetic x402) vs "self reason".

### 2. Letta

**Spec says** (MWGYM-V2-SPEC):
> MWGym learns WHEN to use Letta, not force it everywhere.

**Spec says** (LETTA-MVP-PLAN):
- Persistent agent with memory (MemFS = Git-backed)
- Skills versioned alongside memory
- Background reflection turns workflows into skills
- `createSession(agentId)` for persistent identity

**MWGym has** (`harnesses/letta.py`):
- A class called `LettaAdapter` that makes direct HTTP API calls
- "stateless" mode = single model call (same as direct)
- "stateful" mode = multi-turn conversation with history
- NO actual Letta SDK, NO MemFS, NO Git, NO skills, NO reflection

**Gap**: CRITICAL. We built a wrapper around the OpenCode API and called it "Letta". It doesn't use Letta's agent SDK, memory, skills, or any of its actual capabilities. The 4-arm crossover's "Arm C: letta-stateless" is just another direct model call with a different system prompt.

### 3. HydraDB / LabProjection

**Spec says** (MWGYM-SPEC §6):
> Hydra learns the statistical truth. The agent does not need to reason from scratch — it begins with an evidence-backed prior.

**WorkerKit has** (`hydra/store.py`):
- `LabProjection` — SQLite-backed lab intelligence
- Tables: agents, runs, experiments, insights, worker_versions, etc.
- Queries: `win_rate()`, `profitability_by_model()`, `skill_win_correlation()`

**MWGym has** (`lab_bridge.py`):
- Writes experiment results to WorkerKit's LabProjection
- 360 runs recorded, 18 insights

**Gap**: PARTIALLY WIRED. We write to LabProjection but don't READ from it. The spec says Hydra should provide a "prior" for decision-making. We're not doing that — our genomes don't query past performance to inform current decisions.

### 4. YGO with BATS

**Spec says** (MWGYM-SPEC §11):
> Then add synthetic purchasing:
> pay 10 credits → reveal strong policy recommendation
> 
> Now YGO can test L2 too:
> self reason vs buy expert hint
> 
> You could literally emulate an x402 market inside the game:
> cheap evaluator 1 credit, memory search 2, rollout service 5, expert policy 20, deep search 50

**MWGym has**:
- SHOP items (Hint Card, Power Boost, Shield Spell, Deep Search, Expert Policy)
- Genome strategies that CAN buy from shop
- But genomes score items with hardcoded formulas, not BATS

**Gap**: SIGNIFICANT. The shop exists but genomes don't use BATS to decide whether to buy. The "expert policy" (cost 20 credits) should trigger when BATS determines uncertainty is high.

### 5. DecisionPoint

**Spec says** (MWGYM-SPEC §1):
> Every worker run produces decision points: what to do, what it cost, what the alternatives were, what actually happened.
> This becomes the atomic unit of lab intelligence.

**MWGym has**:
- `DecisionPoint` dataclass with all required fields
- YGO runner creates DecisionPoints per turn
- But DecisionPoints are NOT written to LabProjection

**Gap**: PARTIAL. DecisionPoints exist but aren't in the graph db.

### 6. Git Integration

**Spec says** (MWGYM-SPEC §7):
> Git stores something different. Hydra answers "What empirically tends to work?" Git/skills answer "How do I do it?"
> 
> skills/roblox/low-poly-character/SKILL.md, blender-script.py, validation.py

**MWGym has**: NOTHING Git-related. No skills, no versioning, no MemFS.

**Gap**: COMPLETE MISSING. This is for Level 2+ (Roblox, coding benchmarks).

### 7. WorkerGenome Hierarchy (L0-L3)

**Spec says** (MWGYM-SPEC §10):
- L0: reasoning allocation (think/retrieve/verify/escalate) — BATS territory
- L1: execution allocation (which path/tool/sequence)
- L2: make/buy/lease (self/x402/worker)
- L3: opportunity allocation (which job/continue/abandon)

**MWGym has**:
- `WorkerGenome` with L0 thresholds (think_threshold, retrieve_threshold, etc.)
- But these thresholds aren't connected to BATS or any actual decision-making
- YGO strategies use hardcoded scoring, not genome thresholds

**Gap**: SIGNIFICANT. Genome exists as data but isn't used as a decision policy.

### 8. Promotion Gates

**Spec says** (MWGYM-SPEC §15):
> DEV → YGO improvement → TRANSFER → Roblox/code → SHADOW → historical → CANARY → $1 max → PRODUCTION

**MWGym has** (`promotion.py`):
- `PromotionGate` class with all 5 levels
- Criteria for each level
- `evaluate_and_promote()` method

**Gap**: WIRED but not tested. No genome has been promoted because we haven't run enough games.

## Summary: What ports to Moltwork

| Component | Can port? | What's missing |
|-----------|-----------|----------------|
| WorkerGenome | YES | Thresholds need to connect to BATS |
| DecisionPoint | YES | Need to write to LabProjection |
| BudgetLedger | YES | Working, tracks costs |
| YGO env | YES | Needs BATS integration for L2 decisions |
| Crossover harness | YES | But "Letta" arm is fake |
| LabProjection bridge | YES | Working, writes runs/insights |
| Promotion gates | YES | Need real metrics to trigger |
| BATS | NO | Not used in MWGym at all |
| Letta SDK | NO | Fake adapter, not real Letta |
| Git/skills | NO | Not implemented |
| Hydra prior | NO | Don't read from LabProjection |

## What needs to happen for real Moltwork porting

1. **Wire BATS into YGO** — genomes should use BATS.select_model() to decide when to "buy expert hint"
2. **Wire BATS into crossover** — router should use BATS, not regex
3. **Use real Letta SDK** — persistent agents with MemFS, skills, reflection
4. **Read from LabProjection** — genomes should query past performance before deciding
5. **Write DecisionPoints to graph** — every decision should be recorded
6. **Scale YGO to 1000+ games** — need real win-rate curves for promotion
