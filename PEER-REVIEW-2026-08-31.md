# MWGym Peer Review — Method Comparison with Existing Work

## Our Method

MWGym uses YGO as a controlled environment to learn **resource-rational allocation** — when to use more computation, memory, retrieval, or verification. Key components:

1. **DecisionPoint** — atomic unit capturing what to do, what it cost, alternatives considered
2. **MetaAction space** — ACT_NOW, RETRIEVE, ROLLOUT_4/16, LETTA_REASON, CHEAP/STRONG_MODEL, VERIFY, SUMMARIZE, PIVOT, STOP_SEARCH
3. **ThresholdBudgetAllocator** — baseline using uncertainty thresholds
4. **Thompson allocator** — learns from outcomes via Beta posteriors
5. **ComputeWallet** — shared budget across decisions
6. **DecisionFeatures** — 11 domain-independent features (entropy, margin, irreversibility, stakes, etc.)

## Existing Work Comparison

### 1. YGO Agent (sbl1996/ygo-agent)

**What they do:** Deep RL (PPO) to train card-playing policies. JAX-based, envpool + ygopro-core.

**What we do:** Not training a card-playing policy. Using YGO as a controlled environment to learn **when to allocate resources**.

**Key difference:** They optimize **what move to play**. We optimize **how much computation to spend deciding**. Their policy is the thing being learned. Our policy is frozen; we learn the meta-policy around it.

**Overlap:** Both use YGO as a testbed. Both need the same environment interface.

### 2. YGO-Bench (yugi-bench/yugi-bench-v1)

**What they do:** 217 single-turn-win puzzles. LLM agents use 24 tools to interact with EDOPro/ocgcore engine. Benchmark for tool-use capability.

**What we do:** Not solving puzzles. Learning resource allocation across sequential decisions in full duels.

**Key difference:** They measure **whether the LLM can solve a puzzle**. We measure **whether the allocator can decide when to spend resources**. Their benchmark is about capability. Ours is about economics.

**Overlap:** Both use the same underlying engine (ygopro-core). Could potentially use their puzzle suite as a task family.

### 3. YGO-Bench (erwinmsmith/YGO-Bench)

**What they do:** Dual-LLM duels, visual replay, round-robin Arena, Elo/Glicko-2 ratings.

**What we do:** Not doing LLM-vs-LLM duels. Using a frozen base policy with resource allocation around it.

**Key difference:** They're building a leaderboard for LLM card-playing ability. We're building a lab for learning resource allocation policies.

**Overlap:** Their evaluation metrics (illegal-action rate, latency, tokens) are useful. Their arena format could be adapted for our allocator comparison.

### 4. LLM Card Game Mastery (arxiv 2509.01328)

**What they do:** Fine-tune LLMs on gameplay data for Dou Dizhu, Guandan, Mahjong. Show LLMs can master multiple games.

**What we do:** Not fine-tuning on gameplay data. Learning meta-level resource allocation.

**Key difference:** They're improving **game-playing ability** via fine-tuning. We're improving **resource allocation ability** via experimentation. Their LLMs learn to play better. Our allocators learn when to spend more.

**Overlap:** Their finding that "general learning ability of LLMs is their most significant advantage" aligns with our thesis that resource allocation is transferable across task families.

### 5. Budget-Aware Agentic Routing (arxiv 2602.21227)

**What they do:** Select between cheap/expensive models at each step in long-horizon workflows. Boundary-Guided Training with difficulty taxonomy.

**What we do:** Select between meta-actions (ACT_NOW, ROLLOUT, RETRIEVE, etc.) at each decision point.

**Key difference:** They route between **models**. We route between **meta-actions** (which include models but also retrieval, verification, summarization, etc.). Their action space is {cheap_model, expensive_model}. Ours is {ACT, RETRIEVE, ROLLOUT_4, ROLLOUT_16, LETTA_REASON, CHEAP, STRONG, VERIFY, SUMMARIZE, PIVOT, STOP}.

**Strongest overlap:** Their Boundary-Guided Training concept (using always-cheap and always-expensive boundaries to shape learning) is very similar to our A0 (uniform) and A8 (oracle) baselines. Their finding that "static reward parameters do not fully adapt to varying budget caps" validates our approach of learning allocation policies.

### 6. Route-to-Reason (arxiv 2505.19435)

**What they do:** Dynamically allocate both models AND reasoning strategies (CoT, CoD, PAL, Vanilla) per query.

**What we do:** Dynamically allocate meta-actions per decision point.

**Key difference:** They route at the **query level** (one routing decision per question). We route at the **decision level** (multiple routing decisions per game turn). Their granularity is coarser.

**Strongest overlap:** Their joint allocation of "models × strategies" is conceptually similar to our meta-action space. They show that "selecting the best model and CoT leads to redundant reasoning" — analogous to our finding that the oracle (always ROLLOUT_16) wastes budget.

### 7. Adaptive LLM Routing Under Budget Constraints (PILOT, EMNLP 2025)

**What they do:** Contextual bandit for LLM routing with budget constraints. Shared embedding space for queries and LLMs.

**What we do:** Thompson sampling for meta-action allocation with shared budget.

**Key difference:** They use **LinUCB** (linear bandit). We use **Thompson sampling** (Beta posterior). Their budget is per-query. Ours is per-episode (shared across decisions).

**Strongest overlap:** Their finding that "bandit feedback enables adaptive decision making without exhaustive inference" validates our Thompson approach. Their multi-choice knapsack for budget allocation is similar to our ComputeWallet.

### 8. BudgetMem (arxiv 2602.06025)

**What they do:** Runtime memory framework with budget tiers (Low/Mid/High) for each module. RL-trained router selects tiers.

**What we do:** Runtime resource allocation with meta-actions for each decision point.

**Key difference:** They budget **memory extraction** (how much to compute for memory). We budget **decision-making** (how much to compute for choosing an action). Their modules are memory stages. Ours are meta-actions.

**Strongest overlap:** Their modular budget-tier approach is similar to our meta-action cost table. Their finding that "different tiering strategies provide different trade-offs under varying budgets" validates our multi-allocator comparison.

### 9. Token-Budget-Aware Reasoning (TALE, arxiv 2412.18547)

**What they do:** Dynamically adjust reasoning tokens based on problem complexity. Budget-aware CoT.

**What we do:** Dynamically adjust computation based on decision complexity.

**Key difference:** They control **token count** per reasoning step. We control **which meta-action** to take (which has different token costs). Their control is finer-grained (continuous token budget). Ours is coarser (discrete meta-actions).

**Overlap:** Both address the same fundamental question: "how much reasoning does this problem deserve?" Their finding that "the reasoning process is unnecessarily lengthy and can be compressed" aligns with our finding that ACT_NOW (no extra computation) is often optimal.

### 10. MTG-Causal-RL (arxiv 2605.06066)

**What they do:** Causal RL benchmark on Magic: The Gathering. Structural Causal Model over strategic variables. CGFA-PPO agent.

**What we do:** Resource-rational allocation benchmark on Yu-Gi-Oh.

**Key difference:** They're doing **causal credit assignment** (which factor caused the win?). We're doing **resource allocation** (which meta-action was worth the cost?). Their SCM is over game variables. Our DecisionFeatures are over decision context.

**Strongest overlap:** Both use card games as controlled environments for architectural research. Both emphasize that "scalar win rate alone cannot expose diagnostic structure." Their paired-seed evaluation protocol is similar to ours.

## Where We Fit

The existing landscape has:

1. **YGO playing** (ygo-agent, Galatea-Core) — training policies to play better
2. **YGO benchmarks** (yugi-bench, YGO-Bench) — measuring LLM capability
3. **LLM routing** (BAAR, PILOT, Route-to-Reason) — selecting models per query
4. **Budget-aware reasoning** (TALE, BudgetThinker) — controlling token budgets
5. **Memory budgets** (BudgetMem) — controlling memory extraction cost

**MWGym sits at the intersection of 3, 4, and 5**, but at a **different granularity**:

- LLM routing: per-query decisions → we do per-decision-point decisions
- Token budgets: continuous token control → we do discrete meta-action selection
- Memory budgets: module-level tiers → we do cross-cutting resource allocation

**Our unique contribution:** The meta-action space (ACT, RETRIEVE, ROLLOUT, VERIFY, etc.) is more expressive than model routing alone. It captures the full range of "how much intelligence a problem deserves" — not just which model, but whether to retrieve, verify, summarize, or stop searching.

## Methodological Strengths

1. **Controlled environment** — YGO provides deterministic, reproducible evaluation
2. **Paired seeds** — fair comparison between allocators
3. **Shared budget** — realistic constraint that forces trade-offs
4. **Domain-independent features** — DecisionFeatures enable transfer
5. **Thompson sampling** — principled exploration/exploitation
6. **Telemetry validation** — every cost is tracked, no silent failures

## Methodological Weaknesses

1. **Synthetic YGO** — not using real ygoenv (C++ extension not built)
2. **Simple base policy** — 0% win rate means we're not testing against strong opponents
3. **No real Letta integration** — memory arms are simulated
4. **No real HydraDB** — using SQLite fallback
5. **Small scale** — 100-900 games, not 5,000+
6. **No transfer test** — haven't tested cross-domain yet

## What Would Make This Paper-Worthy

1. **Real ygoenv** — build the C++ extension, get real game mechanics
2. **Stronger base policy** — train a PPO agent, then test allocation around it
3. **Real Letta memory** — persistent agents with MemFS
4. **Real HydraDB** — organizational memory graph
5. **1000+ paired games** — statistical significance
6. **Cross-domain transfer** — test on coding tasks
7. **Allocation regret metric** — compare against empirical oracle
8. **Learning curve AUC** — measure sample efficiency

## Conclusion

Our method is **novel in its meta-action space and granularity** but **similar in spirit to existing budget-aware routing work**. The key differentiator is that we allocate across multiple resource types (memory, retrieval, reasoning, verification, summarization) rather than just models. This is more expressive but also harder to learn.

The strongest existing parallel is **Budget-Aware Agentic Routing (BAAR)**, which shares our budget constraint and sequential decision structure. Our Thompson allocator's 68% win rate (vs 0% for baselines) suggests that learning which meta-actions are worth their cost is feasible — but we need stronger baselines and real environments to make this credible.
