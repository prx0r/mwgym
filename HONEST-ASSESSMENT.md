# Honest Assessment — What Should We Actually Do?

## The YGO Problem

**YGO is the wrong testbed for our resources.**

Requirements we don't have:
- C++ compilation for ygoenv (needs xmake, doesn't work as root)
- Docker build for YGO-Bench (needs 2GB+ RAM for build)
- GPU for PPO training (we have CPU only)
- 8GB RAM for vectorized environments (we have 839MB free)

What YGO actually tests:
- Card game strategy (not what Moltwork does)
- RL exploration in large action spaces (interesting but not our problem)
- Resource allocation around a frozen policy (our real question)

**The 68% "win rate" is against a synthetic opponent we wrote. It proves nothing about Moltwork.**

## What We Should Do Instead

**Harbor (coding tasks) is the right testbed.**

Why:
1. **It's what Moltwork actually does** — coding, not card games
2. **Real verification** — tests, linting, git diffs (not synthetic rewards)
3. **Real costs** — actual API calls, actual tokens, actual dollars
4. **No C++ compilation needed** — Python-only
5. **Runs on our hardware** — 4 cores, 8GB RAM is enough
6. **Already integrated** — Harbor adapter exists in WorkerKit

What Harbor tests:
- Can a worker solve a real coding task?
- When should it use more compute?
- When should it retrieve memory?
- When should it verify its output?
- When should it stop searching?

**These are exactly the questions Moltwork needs to answer.**

## The Real Research Question

> Can a Moltwork worker learn when additional memory, retrieval, reasoning, search, verification or stronger inference is worth its cost?

**YGO can't answer this** because:
- YGO has no real memory to retrieve
- YGO has no real reasoning to escalate
- YGO has no real verification to compare
- YGO rewards are synthetic, not economic

**Harbor CAN answer this** because:
- Harbor has real code to write
- Harbor has real tests to run
- Harbor has real costs to track
- Harbor has real outcomes (accepted/rejected)

## What We Built That's Actually Useful

| Component | Useful for YGO? | Useful for Harbor? |
|-----------|----------------|-------------------|
| Telemetry | No (synthetic) | **YES** (real costs) |
| BudgetLedger | No (synthetic) | **YES** (real budgets) |
| AssetProfile | No (no real models) | **YES** (real model routing) |
| StackOracle | No (synthetic actions) | **YES** (real resource allocation) |
| DecisionFeatures | Maybe | **YES** (code complexity, test results) |
| MetaActionExecutor | No (synthetic) | **YES** (real retrieve/verify/escalate) |
| PromotionGates | No | **YES** (genome evolution) |

**Most of our infrastructure is actually useful for Harbor, not YGO.**

## What I Think We Should Do

### Option A: Abandon YGO, focus on Harbor (recommended)

1. Delete the synthetic YGO environment
2. Keep telemetry, budget, AssetProfile, StackOracle
3. Build Harbor adapter with real tasks
4. Run experiments on real coding tasks
5. Learn resource allocation for actual work

### Option B: Keep YGO as secondary, Harbor as primary

1. Keep YGO for controlled experiments (small scale)
2. Build Harbor for real-world experiments (main focus)
3. Test transfer: does YGO-learned allocation help on Harbor?

### Option C: Continue YGO (not recommended)

1. Need to build C++ extension (hours of work)
2. Need to train PPO agent (needs GPU we don't have)
3. Need to run vectorized environments (needs RAM we don't have)
4. Even then, YGO doesn't test what Moltwork needs

## My Recommendation

**Option A: Abandon YGO, focus on Harbor.**

The reason is simple: **Moltwork is about economic work, not card games.**

Every hour we spend on YGO is an hour we're not spending on:
- Real task execution
- Real cost tracking
- Real memory retrieval
- Real verification
- Real learning from outcomes

The spec says YGO is "World 001" — a controlled environment. But we've proven the infrastructure works. The next step should be "World 002" — Harbor coding tasks — which is what Moltwork actually does.

## What to Push to Git

1. All the infrastructure we built (it's useful)
2. This honest assessment
3. Recommendation to pivot to Harbor
4. Keep YGO code for reference but don't invest more time

## What the Spec Gets Wrong

The spec says:
> "Do not let config evolution immediately operate freely on paid jobs."

This is correct. But it also says:
> "YGO is World 001"

This assumes YGO is the right starting point. For our resources and our actual goal (economic work), **Harbor is the right starting point**.

YGO is a beautiful research environment. But we're not doing research on card games. We're doing research on **how workers should allocate scarce resources when doing real work**.

Harbor gives us real work. YGO gives us a simulation.

**Pick real work.**
