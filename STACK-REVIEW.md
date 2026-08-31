# WorkerKit Stack Review — What We Have, What's Missing, Where to Go

## What's Actually Working (Tested, Verified)

### Runtime Layer
| Component | Status | Location |
|-----------|--------|----------|
| runtime-letta | **UP** on :3000 | `/root/workerkit/services/runtime-letta/` |
| Letta Agent SDK | **WORKING** | Node.js, local backend |
| Worker → Agent mapping | **WORKING** | `data/letta-workers/*.json` |
| New session per run | **WORKING** | Verified in logs |
| Model: mimo-v2.5 | **WORKING** | opencode-go, free tier |

### Execution Layer
| Component | Status | Location |
|-----------|--------|----------|
| FakeWorkerRuntime | **WORKING** | ms-speed orchestration tests |
| MockHarbor | **WORKING** | Docker-free trials + regrade |
| RunBinding | **WORKING** | content-addressed statements |
| Campaign lifecycle | **WORKING** | create/run/grade/regrade/outcome |
| LabBrief | **WORKING** | compounds evidence across campaigns |
| AutomationResolver | **WORKING** | API→MCP→WebMCP→human ladder |

### Intelligence Layer
| Component | Status | Location |
|-----------|--------|----------|
| BATS | **WORKING** | `providers/bats.py` (threshold version) |
| Broker | **WORKING** | `providers/broker.py` (free_first, strong_only) |
| Registry | **WORKING** | `providers/registry.py` (API keys, pricing) |
| LiveLLM | **UP** on :3847 | Real-time pricing data |
| GraphStore | **WORKING** | SQLite with auto-projection |
| HydraDB | **AVAILABLE** | Docker on port 17687 |

### MWGym Infrastructure
| Component | Status | Location |
|-----------|--------|----------|
| Telemetry | **WORKING** | `telemetry_records.py` |
| BudgetLedger | **WORKING** | `core/budget_ledger.py` |
| AssetProfile | **WORKING** | `asset_profile.py` |
| StackOracle | **WORKING** | `stack_oracle.py` |
| ComputeWallet | **WORKING** | `compute_wallet.py` |
| DecisionFeatures | **WORKING** | `decision_features.py` |
| MetaActionExecutor | **WORKING** | `meta_actions.py` |
| PromotionGates | **WORKING** | `promotion.py` |

## What's NOT Wired

| Component | Status | What's Missing |
|-----------|--------|----------------|
| Harbor CLI | MockHarbor only | `harbor run` not called |
| Trace2Skill | vendor/ cloned | Never called |
| GEPA | vendor/ cloned | Never called |
| HydraDB over Bolt | SQLite only | HTTP client ready |
| Real submissions | All synthetic | No real tasks |
| Letta stateful | stateless:true | Config now in WorkerGenome |
| Oracle opportunities | Spec exists | No live feed |

## The Full Stack (What Should Exist)

```
ORACLE → opportunities (what work exists?)
    ↓
WORKERKIT → execution (how to do it?)
    ↓
MWGym → experiments (what works best?)
    ↓
┌───────────┬───────────┬───────────┐
│ Harbor    │ Roblox    │ Live jobs │
│ coding    │ asset     │ Oracle    │
│ tasks     │ work      │ opport-   │
│           │           │ unities   │
└───────────┴───────────┴───────────┘
```

## What We Should Do Next

### Priority 1: Wire Harbor for Real Tasks (1-2 days)

Harbor already exists in WorkerKit. We need to:
1. Create real Harbor tasks (coding challenges)
2. Wire `harbor run` (not MockHarbor)
3. Track real costs via TelemetryStore
4. Record outcomes in LabProjection

### Priority 2: Wire Letta Stateful (already done in code)

The runtime-letta fix is already committed:
- `stateless` comes from `genomeConfig.memory_mode`
- `maxSteps` comes from `genomeConfig.max_steps`
- Need to test with `memory_mode: "letta"` (stateful)

### Priority 3: Wire HydraDB (when disk space allows)

HydraDB Docker is running but has disk issues. When fixed:
- Write DecisionPoints as graph nodes
- Query past performance for routing
- Track genome lineage

### Priority 4: Build Real Allocator (not YGO)

The StackOracle, AssetProfile, ComputeWallet are ready.
Wire them to real tasks:
- AssetProfile tracks success/failure per model per task family
- StackOracle uses Thompson sampling to select models
- ComputeWallet tracks real costs

## The Honest Gap

We have **infrastructure** but no **experiments**.

The handover says:
> 91/91 workerkit invariants PASS
> 17/17 Letta adapter tests PASS
> E2E: opportunity → campaign → run → grade → regrade → graph PASS

But these are all **unit tests and mocks**. The real question is:

> Does a Letta worker with persistent memory perform better on real tasks than one without?

We haven't tested this yet.

## What to Build in MWGym (Revised)

**Not YGO. Harbor coding tasks.**

```
MWGym-Harbor
    │
    ├── Task: "Write a Python function that..."
    │
    ├── Arms:
    │   A: Direct (no memory)
    │   B: Letta stateless
    │   C: Letta persistent
    │   D: Letta + Hydra retrieval
    │   E: StackOracle (Thompson)
    │
    ├── Metrics:
    │   - Success rate
    │   - Tokens used
    │   - Cost
    │   - Latency
    │   - Memory hit rate
    │
    └── Environment:
        Harbor (real coding tasks)
        Not YGO (synthetic card game)
```

## Immediate Action Items

1. **Create 10 Harbor coding tasks** (simple Python functions)
2. **Run 5-arm crossover** (direct, letta-stateless, letta-persistent, letta+hydra, stack-oracle)
3. **Track real costs** via TelemetryStore
4. **Record in LabProjection**
5. **Produce report with REAL results**

This is what MWGym should be doing.
