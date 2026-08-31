# MWGym Build Report — 2026-08-31 16:00 UTC

## The Vision (from QDW/Moltwork spec)

The system should be an **economic operating system for cognition**:

```
JOB → EconomicEnvelope → PlanGraph → DecisionPoint → StackOracle → CapabilityAssets → outcome → learn
```

Key principles:
1. Never buy cognition you already possess
2. Capability routing > model routing
3. Route each consequential decision, not each job
4. Separate worker from treasury
5. Cheapest acceptable intelligence, not cheapest intelligence
6. Verification changes economics of intelligence
7. Free quota is perishable inventory
8. One shared wallet, not N independent budgets

## What MWGym Has Built vs What the Spec Requires

### Layer 1: Ontology (QDW primitives)

| QDW Primitive | Spec says | MWGym status | Gap |
|---------------|-----------|--------------|-----|
| `CapabilityAsset` | Routable supply (model, API, tool, human) | WorkerGenome exists but is config-only | Need CapabilityAsset for routing |
| `CapabilityLease` | Call limits, spend limits, expiration | BudgetLedger tracks spending | Need lease/expiration logic |
| `Invocation` | Immutable outcome record | DecisionPoint exists, written to LabProjection | Partial — need invocation format |
| `AssetProfile` | Beta success posterior + cost history | Not implemented | Need Thompson sampling |
| `HumanOracle` | Humans as another capability | Not implemented | Need for Level 4+ |
| `DataRightsBackend` | Privacy/licensing as routing constraints | Not implemented | Need for real jobs |
| `StackOracle` | Generalized LLM/tool/human/data allocator | BATS exists but is model-only | Need full StackOracle |
| `TechniqueCandidate` | Pluggable routing algorithms | Not implemented | Need for policy evolution |
| `RepoBenchTask` | Historical tasks as evaluation substrate | YGO tasks exist but synthetic | Need real task corpus |

### Layer 2: Economic Control (LiveLLM integration)

| Component | Spec says | MWGym status | Gap |
|-----------|-----------|--------------|-----|
| LiveLLM market state | Real-time pricing, promotions, free-tier | MarketClient exists with hardcoded defaults | Need live LiveLLM feed |
| `ComputeWallet` | Cash, quotas, credits, local compute | BudgetLedger exists but simple | Need multi-source wallet |
| Quota management | Free quota is perishable inventory | Not implemented | Need expiration tracking |
| Risk classes | Asymmetric risk, CVaR | Not implemented | Need for high-value jobs |
| Exploration quota | Counterfactual exploration to avoid selection bias | BATS has exploration_rate | Need structured exploration |

### Layer 3: Routing Policy

| Policy | Spec says | MWGym status | Gap |
|--------|-----------|--------------|-----|
| `strong_only` | Quality ceiling/control | Not tested | Need as baseline |
| `cheap_only` | Lower bound | direct-fast is this | ✓ Have |
| `free_first` | Naive economic baseline | BATS default_free is this | ✓ Have |
| `route_llm` | Established model-router baseline | Router exists with BATS | Partial |
| `selective_ensemble` | Cheap disagreement → strong judge | Not implemented | Need Avengers policy |
| `shadow_price` | Shared wallet + quota scarcity | Not implemented | Need |
| `thompson_stack` | Forge posterior + prices | AssetProfile not implemented | Need Beta posterior |
| `oracle_distilled` | Learn from empirical optimal | LabProjection queries exist | Partial |
| `full_stack_oracle` | All resource classes + Hydra | Not implemented | Need |

### Layer 4: YGO World

| Component | Spec says | MWGym status | Gap |
|-----------|-----------|--------------|-----|
| YGO env | Closed deterministic world for L0/L1 testing | Working, balanced | ✓ Have |
| Opponent strategies | Passive, aggressive, defensive, economic | 4 strategies implemented | ✓ Have |
| Shop (synthetic x402) | Pay credits → reveal strong policy | Working, BATS decides purchases | ✓ Have |
| BATS integration | should_escalate, should_branch | Working in YGO strategies | ✓ Have |
| DecisionPoints | Atomic unit of lab intelligence | Written to LabProjection | ✓ Have |
| Genome evolution | Mutation, selection, promotion | Promotion gates exist, untested | Need |
| 1000+ games | Statistical significance | Ran 120 games | Need scale |

### Layer 5: Letta Integration

| Component | Spec says | MWGym status | Gap |
|-----------|-----------|--------------|-----|
| Persistent agents | MemFS, Git-backed memory | Runtime-letta on port 3000 | ✓ Have |
| Worker → Agent mapping | Persistent identity across sessions | Working (mwgym-test-worker created) | ✓ Have |
| New session per run | Don't reuse conversations | Implemented in real_letta.py | ✓ Have |
| Trajectory export | `@letta-ai/trajectory` for learning | Not wired | Need |
| Skills | Agent-owned reusable procedures | Not implemented | Need |
| Reflection/dreaming | Background learning | Not implemented | Need |

### Layer 6: HydraDB

| Component | Spec says | MWGym status | Gap |
|-----------|-----------|--------------|-----|
| Graph nodes | Worker, Run, Decision, Outcome, Skill | HydrBridge writes nodes | Partial |
| Graph edges | EXECUTED_BY, CONTAINS, RESULT_OF | Edges created | Partial |
| Cypher queries | "What decisions led to wins?" | SQLite queries work | Need Bolt |
| Empirical priors | "What worked before?" | LabProjection queries work | ✓ Have |
| Selection bias control | Counterfactual exploration | Not implemented | Need |

## What's Actually Working (End-to-End)

### Loop 1: YGO → BATS → DecisionPoint → LabProjection ✓
```
YGO game starts
  → YGOStrategy queries LabProjection for Hydra prior
  → BATS.should_escalate() decides if Expert Policy purchase is worth it
  → BATS.should_branch() decides if exploration is warranted
  → Action taken, reward observed
  → DecisionPoint written to LabProjection with full context
  → Game ends, outcome recorded
```

### Loop 2: Crossover → Router → BATS → Direct/Fast ✓
```
Task arrives
  → DynamicRouter.classify() computes uncertainty
  → BATS.should_escalate() decides direct-fast vs fast-bundle
  → Appropriate harness executes
  → Result recorded with BATS context
```

### Loop 3: Runtime-Letta → Worker → Session ✓
```
Worker ID → Letta Agent ID mapping
  → New session created for each run
  → Task executed via Letta Code backend
  → Result returned (files created)
  → Session closed
```

## What's NOT Working End-to-End

### Missing Loop: LiveLLM → StackOracle → Routing
```
LiveLLM detects price change
  → Should trigger StackOracle re-evaluation
  → Should update routing policy
  → NOT WIRED
```

### Missing Loop: Hydra → Empirical Prior → Router
```
Hydra has 480 runs of data
  → Router should query "what worked for similar tasks?"
  → Should influence routing decision
  → PARTIALLY WIRED (LabProjection queries exist, router doesn't use them)
```

### Missing Loop: Trajectory → Trace2Skill → Skill
```
Letta produces trajectory
  → Should feed to Trace2Skill
  → Should extract reusable skill
  → Should promote to MemFS
  → NOT WIRED
```

### Missing Loop: Exploration → Counterfactual → Unbiased Learning
```
Router gets good at routing
  → Stops exploring alternatives
  → Selection bias makes Hydra data unreliable
  → Need structured exploration quota
  → NOT IMPLEMENTED
```

## Concrete Next Steps (Prioritized)

### Step 1: Fix HydraDB disk, wire graph queries (1 day)
HydraDB Docker has "No space left on device". Fix it, then:
- Write DecisionPoints as `Decision` nodes
- Connect to `Run` nodes via `CONTAINS` edges
- Query: "What decisions correlated with wins?"
- Feed results back to router

### Step 2: Build AssetProfile with Beta posterior (2 days)
Implement Thompson sampling for capability routing:
```python
class AssetProfile:
    alpha: int = 1  # successes
    beta: int = 1   # failures
    
    def sample(self) -> float:
        return beta_sample(self.alpha, self.beta)
    
    def update(self, success: bool):
        if success: self.alpha += 1
        else: self.beta += 1
```
Each genome/harness/model gets an AssetProfile. Router samples from posteriors.

### Step 3: Wire LiveLLM into StackOracle (1 day)
- LiveLLM provides real-time pricing
- StackOracle uses prices + AssetProfile posteriors
- Thompson sampling picks capability based on expected utility
- Free quota tracked with expiration

### Step 4: Run YGO 1000-game experiment (1 day)
- 1000 games × 3 genomes × 4 opponents
- BATS integration active
- DecisionPoints written to graph
- Win-rate curves computed
- Promotion gates evaluated

### Step 5: Build selective ensemble (Avengers) policy (2 days)
```
Task → 3 cheap workers → agreement?
  → yes: accept
  → no: frontier arbiter
```
Test on YGO: do multiple cheap genomes agree on action?

### Step 6: Wire trajectory → Trace2Skill (3 days)
- Export Letta trajectories
- Feed to Trace2Skill
- Extract reusable skills
- Promote to MemFS
- Test: does skill improve future performance?

### Step 7: Run real crossover with Letta arm (2 days)
- 10 tasks × 4 arms (direct, fast, real-letta, router)
- Real Letta creates persistent agent
- Compare: cheap vs artifacts vs persistent learning

### Step 8: Add exploration quota (1 day)
- 10% of routing decisions go against recommendation
- Track counterfactual outcomes
- Use inverse propensity weighting for unbiased learning

### Step 9: Build ComputeWallet with quota expiration (2 days)
- Track: cash, Groq quota, OpenCode credits, local compute
- Free quota has expiration time
- Expired quota → sweep backlog for low-risk tasks
- Quota scarcity → shadow price increases

### Step 10: Run profit-optimized experiment (3 days)
- Same work corpus, different routing policies
- Measure: net profit, not just accuracy
- Policies: strong_only, free_first, thompson, avengers, full_stack
- Headline metric: `verified_value / total_cost`

## The One-Sentence Summary

> MWGym has built the measurement layer (YGO, BATS, DecisionPoints, LabProjection) but not the economic control layer (StackOracle, AssetProfile, LiveLLM integration, exploration quota, profit optimization).

The next phase is making the StackOracle the canonical allocation interface that routes capabilities (not just models) based on empirical posteriors (not just benchmarks) to maximize profit (not just accuracy).
