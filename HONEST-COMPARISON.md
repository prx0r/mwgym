# What We Actually Have — Honest Comparison

## CG (cogymkernel) — THE ACTUAL LAB

**Status:** Working. 31 tests pass. CLI runs real episodes.

```bash
cd /root/cg
python3 -m pytest tests/ -q          # 31 passed
python3 -m cogym_kernel.cli status   # kernel + hydra health
python3 -m cogym_kernel.cli worlds   # toy.signal_game
python3 -m cogym_kernel.cli run --world toy.signal_game --seed 42
```

**What it has:**
- Deterministic worlds (worldpack format)
- Content-addressed run IDs (blake3 hash)
- Quality gates (hard constraints, not scalar fitness)
- Experience graph (HydraDB, when available)
- Evolution recipes (10 recipes, 33 reasoning styles)
- Async execution (500+ eps/min target)
- Event sourcing (JSONL receipts)
- Sealed evaluation (evaluator owns labels)

**What it doesn't have:**
- HydraDB running (SQLite fallback)
- Letta integration
- Real Harbor tasks
- LLM-based evolution

## CGE — Same as CG

CGE appears to be the same codebase as CG. Same files, same tests, same spec.

## MWGym — INFRASTRUCTURE SCAFFOLDING

**Status:** Components built but no real experiments.

**What it has:**
- Telemetry (ModelCallRecord, ResourceSpend)
- BudgetLedger, AssetProfile, StackOracle
- ComputeWallet, DecisionFeatures, MetaActionExecutor
- LabBridge (SQLite degraded)
- Harbor tasks (10 Python coding tasks)
- Real Letta adapter (timing issues)

**What it doesn't have:**
- Real experiments that prove anything
- Working YGO (C++ extension not built)
- Working Harbor integration (timeout issues)
- HydraDB (disk full)

## The Honest Truth

**CG is the lab. MWGym is scaffolding.**

CG already has:
- Deterministic worlds ✓
- Content-addressed runs ✓
- Quality gates ✓
- Evolution recipes ✓
- Async execution ✓
- Event sourcing ✓

MWGym has:
- Telemetry ✓
- Budget tracking ✓
- StackOracle ✓
- But no real experiments

## What We Should Do

### Option 1: Use CG as the lab (recommended)

CG is already working. We should:
1. Use CG's worldpack format for Harbor tasks
2. Use CG's evolution recipes for genome evolution
3. Use CG's event sourcing for experiment tracking
4. Add Letta integration to CG
5. Add MWGym's StackOracle to CG's evolution

### Option 2: Merge MWGym into CG

MWGym's unique contributions:
- StackOracle (Thompson allocator)
- AssetProfile (Beta posteriors)
- ComputeWallet (multi-source budget)
- DecisionFeatures (domain-independent features)

These could become CG evolution recipes or worldpack modules.

### Option 3: Keep separate (not recommended)

MWGym and CG solving similar problems independently is wasteful.

## My Recommendation

**Abandon MWGym as a separate project. Use CG as the lab.**

MWGym's useful components (StackOracle, AssetProfile, ComputeWallet) should become CG evolution recipes or worldpack modules.

The real work is:
1. Wire Letta into CG
2. Create Harbor worldpacks
3. Run evolution campaigns
4. Track results with CG's event sourcing

CG already has the infrastructure we were trying to build.
