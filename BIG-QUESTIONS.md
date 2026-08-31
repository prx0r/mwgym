# MWGym Big Questions — Get External Opinion

**Date:** 2026-08-31
**Purpose:** Capture all open architectural decisions for external review

---

## 1. Which codebase is the actual lab?

We have three overlapping codebases:

| Repo | What it is | Tests | Status |
|------|-----------|-------|--------|
| **CG** (cogymkernel) | Deterministic evolution lab | 31 pass | Working, runs episodes |
| **CGE** (copy of CG) | Same as CG | 54 pass | More tests |
| **CGE1** | Objective evolution kernel | 6 pass | Clean, minimal |
| **MWGym** | Infrastructure scaffold | 0 | Components built, no experiments |

**Question:** Which one do we actually use?
- CG has the infrastructure (worldpacks, event sourcing, evolution recipes)
- CGE1 has the evolution logic (shrinkage fitness, gates, constraints)
- MWGym has the economic primitives (StackOracle, AssetProfile, BudgetLedger)

**My take:** CG is the lab. CGE1 is the evolution engine. MWGym components should become CG evolution recipes.

**But:** CG and CGE are identical repos (same SPEC, same code). Why do both exist?

---

## 2. Is HydraDB the right experience graph?

CG has a HydraDB client that writes to a graph database.
But HydraDB Docker has disk space issues and the HTTP API is flaky.

**Options:**
- Fix HydraDB Docker (disk cleanup)
- Use SQLite as primary (CG already has GraphStore)
- Use a different graph DB (Neo4j, ArangoDB)
- Skip graph DB entirely, use JSONL receipts + queries

**Question:** Do we need a graph DB at all? Or is JSONL + SQLite enough for the experience layer?

---

## 3. Is Letta the right memory system?

Current state:
- runtime-letta is running on :3000
- It works but is SLOW (35-120s per run)
- No actual memory persistence tested
- No trajectory export wired

**Alternatives:**
- **Letta** — persistent agents, MemFS, skills, reflection (current choice)
- **Pydantic AI** — typed agents, structured output, faster
- **LangChain** — memory, retrieval, chains
- **Custom** — simple file-based memory with SQLite

**Question:** Is Letta's complexity worth it? Or should we use simpler memory (SQLite + files)?

**The slow part:** Letta does 5+ reasoning passes per turn. That's 5 API calls when we only need 1. Can we disable reasoning for routine tasks?

---

## 4. What's the actual feedback loop?

The spec says:
```
CG runs episode → CGE1 evolves → Letta reflects → next episode benefits
```

But nothing is wired:
- CG writes JSONL receipts (working)
- CGE1 is separate from CG (not imported)
- Letta is separate from CG (not connected)
- Nobody reads the receipts to learn

**Question:** What's the minimum viable feedback loop?

**Option A:** CG + SQLite (no HydraDB, no Letta)
```
CG episode → JSONL receipt → SQLite query → next candidate
```

**Option B:** CG + CGE1 + SQLite
```
CG episode → CGE1 scores → SQLite stores → CGE1 proposes next
```

**Option C:** Full stack (CG + CGE1 + Letta + HydraDB)
```
CG episode → CGE1 scores → Letta reflects → HydraDB stores → next episode
```

**My take:** Start with Option A, add complexity only when needed.

---

## 5. How do we classify job offers?

We built a classifier (job_classifier.py) that maps Oracle offers → CG world types.

**Two dimensions:**
- Process Type → which CG world (api_endpoint, game_dev, etc.)
- Autonomy Level → how much can be automated (H0-H4)

**But:** Is this the right abstraction? Or should we classify by:
- Market type (prize, royalty, bounty)?
- Verification strength (H0 eval, H1 review, H2 human)?
- Task complexity (easy, medium, hard)?

**Question:** What's the right way to route Oracle offers to CG worlds?

---

## 6. What's the economic model?

The spec says:
> "Route against profit, not benchmark accuracy"

But we haven't defined:
- What's the revenue model for each world type?
- How do we track actual profit per episode?
- How do we handle costs that exceed revenue?
- What's the minimum viable profit per episode?

**Question:** What's the economic model for each CG world type?

---

## 7. How do we handle exploration vs exploitation?

The StackOracle uses Thompson sampling for exploration.
But we haven't tested if exploration actually helps.

**Open questions:**
- What's the right exploration rate? (currently 10%)
- How do we prevent exploration from burning budget?
- When should we stop exploring and just exploit?
- How do we measure if exploration is worth its cost?

---

## 8. What's the right evaluation protocol?

The spec says:
> "Pair every comparison. Same seed, same opponent, same budget."

But we haven't defined:
- How many seeds per comparison?
- What's the minimum sample size for statistical significance?
- How do we handle variance in LLM outputs?
- What's the right confidence interval?

**Question:** What's the evaluation protocol that produces credible results?

---

## 9. How do we transfer learning across worlds?

The spec says:
> "The transferable object is: WHEN TO ACT, WHEN TO RETRIEVE, WHEN TO THINK..."

But we haven't tested:
- Does a policy learned on API endpoints help on browser extensions?
- Does forecasting skill transfer to coding tasks?
- What features are truly domain-independent?

**Question:** What's the evidence that resource allocation policies transfer?

---

## 10. What's the minimum viable product?

We have:
- 3 codebases (CG, CGE, CGE1)
- 16 MWGym components
- 30 ranked markets
- 18 skill families
- 10 CG world types

But no experiments that prove anything.

**Question:** What's the one experiment that would prove the architecture works?

**My take:** 
1. Take 10 API endpoint tasks from Oracle
2. Run 5 allocators (uniform, threshold, thompson, ensemble, oracle)
3. Measure: success rate, cost, latency
4. If Thompson beats uniform, the architecture works
5. If not, we're building infrastructure for nothing

---

## Summary of Questions

| # | Question | Priority | My Take |
|---|----------|----------|---------|
| 1 | Which codebase? | HIGH | CG + CGE1 |
| 2 | HydraDB or SQLite? | MEDIUM | SQLite first |
| 3 | Letta or simpler memory? | HIGH | Test Letta, fallback to SQLite |
| 4 | Minimum feedback loop? | HIGH | CG + SQLite |
| 5 | Job classification? | MEDIUM | Process type × autonomy |
| 6 | Economic model? | HIGH | Need to define revenue per world |
| 7 | Exploration rate? | MEDIUM | Test 5%, 10%, 20% |
| 8 | Evaluation protocol? | HIGH | Paired seeds, n≥30 |
| 9 | Transfer learning? | LOW | Need evidence first |
| 10 | Minimum viable experiment? | HIGH | 10 tasks × 5 allocators |

---

**Push this to git and get external opinion on the 10 questions.**
