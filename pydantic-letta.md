The main conclusion is clear:

> **Do not throw Letta away, and do not make Letta the mandatory execution loop.**
>
> Make **MWGym the lab**, **PydanticAI the default controllable execution harness**, and **Letta the persistent/stateful worker harness you test when persistence is actually valuable**.

That gives you the flexibility you want without giving up the thing that makes Letta interesting.

One limitation on the push review: the connected GitHub app currently returns 404 for `prx0r/mwgym`, including commit `580d17f`, so I cannot inspect the unseen diff itself. I can review the 10 questions and changes you pasted, plus the accessible `CG/CGE/CGE1` repos and the current upstream frameworks.

## First: the confusion about Letta

There are two separate issues getting mixed together.

### 1. A tool-using agent fundamentally needs multiple model requests

Suppose an LLM does:

```text
LLM request #1
"I should read foo.py"
        ↓
Read(foo.py)
        ↓
LLM request #2
"Now I understand it; edit line 30"
        ↓
Edit(...)
        ↓
LLM request #3
"Now run tests"
        ↓
pytest
        ↓
LLM request #4
"Tests failed. Fix..."
```

No framework can magically turn that into **one ordinary inference request**, because request #1 cannot know the result of `Read()` before it occurs.

PydanticAI, LangGraph, Letta, Hermes: traditional tool loops all have this property.

So if the requirement is literally:

> **one LLM API request**

then one of these must be true:

```text
A. no interactive tools

B. tools/context are run BEFORE the model call

C. model produces a complete program/plan which the host
   executes without asking the model again

D. one tool call internally performs a huge workflow
```

The mistake has been expecting a fully autonomous Letta Code agent to behave like A while giving it Coder-style tools.

### 2. Your stream counts still may not equal model-request counts

This is worth fixing in `BIG-QUESTIONS.md`.

Letta's SDK reasoning/assistant streaming events are append-only fragments. Counting `reasoning` and `assistant` events does **not** reliably count provider inference requests. That precise SDK behavior is currently documented poorly enough that there is an open issue about it. ([GitHub][1])

So:

```text
"5 reasoning messages"
```

does not necessarily mean:

```text
5 HTTP LLM requests
```

Instrument actual provider requests.

If you've done that and there really are five model invocations, then yes: you're observing the agent loop.

---

# Is Letta being used incorrectly?

**Partly.**

You're currently asking the full Letta agent harness to do work that often doesn't need a full agent loop.

Letta's current API explicitly distinguishes a persistent **agent**, conversations on that agent, and runtime sessions. It also supports request-scoped toolsets, including `base: "none"` so you can strip the normal coding harness down. ([GitHub][2])

So your first missing experiment is:

```text
persistent Letta agent
+
toolset.base = none
+
allowedTools = []
+
reasoningEffort = low
+
dreaming disabled
+
strict structured output
```

Then ask:

```text
Return:
{
  "answer": ...,
  "writes": [...],
  "commands": [...]
}
```

Moltwork applies the actions.

That is the correct **Letta-fast** test.

If that produces:

```text
1 real provider request
3-8 seconds
```

great.

Letta was not inherently slow; the coding-agent harness was.

If that still produces:

```text
5 actual requests
35-120 seconds
```

then **Letta should not be the fast execution path**.

Don't argue philosophically about it. MWGym records the result.

---

# The important problem: Letta doesn't currently give you the hard control Pydantic does

This is where PydanticAI is extremely attractive for Moltwork.

PydanticAI currently has a literal:

```python
UsageLimits(
    request_limit=1,
)
```

and it checks that limit **before every model request**. It also tracks actual model requests, tool calls, tokens and cost.

That's exactly the primitive MWGym needs.

You can define:

```yaml
fast:
  request_limit: 1

bounded:
  request_limit: 3

agentic:
  request_limit: 20
```

and actually enforce it.

The current documented Letta Agent SDK session controls include model, reasoning effort, cwd, permissions, tools and dreaming, but there isn't an equivalent documented hard `request_limit=1` session control. ([GitHub][2])

That is a substantive architectural advantage for PydanticAI **for experimentation and economic control**.

---

# And PydanticAI has almost exactly built the optimization you want

This was the strongest thing I found.

PydanticAI Harness now has **DynamicWorkflow**.

They explicitly describe your problem:

> An orchestrator calling ten sub-agents conventionally incurs ten model round-trips.

Their solution is that the orchestrator writes **one Python workflow**, then multiple sub-agents can fan out/chained inside one tool invocation. `max_agent_calls` is host-enforced and sub-agent usage rolls into parent usage. ([GitHub][3])

Think:

```text
STRONG PLANNER
one inference
      │
      ▼
Python workflow
      │
 ┌────┼─────────┬──────────┐
 ▼    ▼         ▼          ▼
FREE  FREE      FREE       FREE
LLM   LLM       LLM        LLM
 │     │         │          │
 └─────┴─────────┴──────────┘
             │
             ▼
       deterministic
          workflow
```

That is astonishingly close to the Moltwork compute thesis.

Pydantic's **CodeMode** similarly turns many tool operations into one `run_code` call rather than forcing the top-level model to micromanage each operation. ([GitHub][3])

So your instinct is right:

> **The orchestration layer needs to let a strong model spend one expensive thought deciding how lots of cheap/free work gets done.**

PydanticAI is currently more naturally shaped for that than the Letta Code loop.

---

# But Pydantic has also caught up substantially on persistence

This was another reason I changed my weighting.

Current PydanticAI Harness now lists as shipped:

* persistent namespaced Memory;
* session persistence;
* checkpoint/resume/fork;
* conversation search;
* Skills;
* Planning;
* SubAgents;
* DynamicWorkflow;
* request/token/tool budgets;
* per-model cost tracking. ([GitHub][3])

So the old argument:

```text
Pydantic = lightweight stateless execution
Letta = only serious persistent agent
```

is no longer really true.

Letta remains more opinionated around the concept of **a durable agent identity that learns**, which is useful. But Pydantic can now implement a very credible persistent Moltwork worker too.

This makes benchmarking them worthwhile.

---

# GBrain is different

Do not treat GBrain as a Letta/Pydantic competitor.

The current original project describes itself explicitly as a **brain layer you place underneath an autonomous agent**, and supports wiring into agents via MCP. ([GitHub][4])

Its strengths are:

```text
durable knowledge
hybrid retrieval
graph traversal
entity relationships
citations
gap analysis
cross-agent shared knowledge
```

It can expose a tiny five-verb memory protocol:

```text
recall
remember
entity
synthesize
forget
```

rather than its full tool surface. ([GitHub][4])

That's interesting.

But it does not answer:

```text
How many inference requests should this run use?

Should this task go to free GLM?

Should I branch into 8 candidates?

Which workflow should execute?

Should I stop?
```

So:

```text
Pydantic / Letta = harness/runtime

GBrain = knowledge substrate
```

I would **not add GBrain to MWGym core yet** because you already have Letta memory + Hydra evidence + Git/MemFS.

Otherwise you get four competing memories before proving one feedback loop.

Later, GBrain is a fascinating retrieval challenger:

```text
Experiment:
Letta native memory
vs
Pydantic Memory
vs
GBrain retrieval
vs
Hydra LabBrief
vs
combinations
```

But not M0.

---

# My decision on your 10 Big Questions

## 1. Which codebase?

**MWGym wins. Freeze CG/CGE/CGE1 as source material.**

`CG` and `CGE` are currently so overlapping that their README files are literally the same content and SHA. Both describe the same deterministic evolution laboratory with worldpacks, eval, Hydra, evolution recipes, SQLite orchestration and science layer.

`CGE1` is genuinely different: it is a much narrower objective-evolution kernel centered on shrinkage scoring, replace-if-wins, constraints and noisy-small-sample optimization.

So don't maintain four laboratories.

Use:

```text
MWGym
  canonical experimental system

archive/reference:
  CG
  CGE
  CGE1
```

Steal specific components:

```text
CGE1:
shrinkage scoring
replace-if-wins
constraint ledger

CGE:
scoring feedback
peer review
MAP-Elites ideas

CG:
receipts
determinism
world/eval patterns
```

Then stop developing those repos independently.

---

# 2. HydraDB or SQLite?

**SQLite canonical. Hydra projection.**

Your own CG README already has the right principle: execution remains functional without Hydra, receipts stay local, and profiles can be flushed later.

Use:

```text
WorkerKit events
     ↓
SQLite/WAL
CANONICAL
     │
     ├──── rebuild ───→ HydraDB
     │
     └──── analytics
```

Hydra being flaky should never prevent an experiment.

Hydra is valuable for:

```text
relationships
similar-run lookup
capability graph
cross-worker experience
organizational memory
```

SQLite is better for:

```text
transactional truth
runs
receipts
experiment arms
model calls
costs
quota ledger
reproducibility
```

Do both, but make only one required.

---

# 3. Letta or Pydantic?

My answer has changed to:

> **Both, but PydanticAI should become the reference/default harness for MWGym. Letta should be the stateful challenger.**

Not because Letta is bad.

Because an experimental lab absolutely needs:

```text
request_limit=1
request_limit=2
request_limit=3
exact cost tracking
clean model switching
arbitrary submodels
easy workflow composition
```

Pydantic currently exposes these knobs more cleanly.

Letta becomes an experimental variable:

```text
Does Letta persistence outperform
Pydantic Memory
enough to justify its overhead?
```

That is far better than assuming it does.

---

# 4. Minimum feedback loop?

Your document apparently says nothing is wired.

Then cut brutally.

The first loop is **not learning memory**.

Do:

```text
ONE World
ONE frozen WorkerGenome
ONE frozen evaluator
10-20 tasks

             ↓

FREE
free models only

OPTIMIZED
free + selective paid

CEILING
strong model

             ↓

real execution
             ↓
WorkerKit receipt
             ↓
SQLite
             ↓
score / cost / latency
```

If that doesn't work, everything else is fiction.

Then add persistence.

---

# 5. Job classification?

`process type × autonomy level` is useful, but incomplete for compute routing.

I would use:

```text
TaskFamily
    coding
    research
    extraction
    evaluation
    planning
    negotiation
    etc.

Stage
    discover
    plan
    generate
    execute
    verify
    synthesize

Autonomy
    H0-H4

EconomicRisk
    low / medium / high
```

**Stage matters enormously.**

Your experiments may find:

```text
planning → strong
extraction → free
generation → cheap
verification → different strong model
```

even within the same job.

---

# 6. Economic model?

Don't define “revenue per World” yet.

Worlds should have:

```text
quality
success
cost
latency
human_time
```

Real WorkOrders add:

```text
estimated_value_usd
```

Then utility becomes:

```text
expected utility =
P(success) × task value

− model cost
− quota shadow cost
− human cost
− latency penalty
```

No fake revenue numbers.

---

# 7. Exploration rate?

**Delete the hard-coded 10%.**

It should eventually be contextual.

Free resources should dramatically increase exploration:

```text
high uncertainty
+
free compute near expiry
=
explore aggressively
```

While:

```text
high-value production task
+
known winning policy
=
exploit
```

Start with Thompson sampling/UCB later.

For M0:

```text
production = fixed policy
free background capacity = experiments
```

Much easier.

---

# 8. n ≥ 30?

Don't make `30` sacred.

Use:

```text
n=5
plumbing

n=10
smoke / large-effect detection

n=20-30
pilot comparison

n=50+
serious promotion claims
```

Always paired where possible:

```text
same task
same seed
same initial state
same assessor
different treatment
```

Then paired bootstrap CI / permutation tests / Bayesian estimate.

A huge effect at `n=10` can justify further experimentation.

A 0.5% effect at `n=30` proves almost nothing.

---

# 9. Transfer learning?

Correct answer:

> **Assume zero transfer until measured.**

Store:

```text
source_task_family
target_task_family
```

Training experience from:

```text
YGO
```

doesn't magically improve:

```text
hackathon coding
```

But perhaps improvements in:

```text
search
planning
budgeting
verification
```

transfer.

That's itself an MWGym experiment.

---

# 10. Minimum experiment?

I would **not** do:

```text
10 tasks × 5 allocators
```

yet.

Too many degrees of freedom.

Do:

```text
15 tasks
×
3 policies
=
45 runs
```

Policies:

```text
F = best free-only

M = free-first + simple escalation

Q = strong-only ceiling
```

One harness first: **PydanticAI**.

Then repeat the exact matrix with Letta.

That immediately answers whether Letta's overhead buys anything.

---

# The architecture I would build now

This is the important piece.

```text
                         MWGYM
                    experiment owner
                           │
                           ▼
                      WorkOrder
                           │
                    frozen context
                           │
          ┌────────────────┴─────────────────┐
          │                                  │
          ▼                                  ▼
    WorkerGenome                       ComputePolicy
 identity/cognition                    economics
 memory policy                         routing
 skills                                budgets
 harness                               escalation
          │                                  │
          └────────────────┬─────────────────┘
                           ▼
                     HarnessAdapter
              ┌────────────┼─────────────┐
              ▼            ▼             ▼
           DIRECT       PYDANTIC       LETTA
          baseline       default       stateful
              │            │             │
              └────────────┼─────────────┘
                           ▼
                     ComputeBroker
                           │
              LiveLLM + Treasury + Hydra
                           │
       ┌───────────────────┼──────────────────┐
       ▼                   ▼                  ▼
      FREE                CHEAP             STRONG
       │                   │                  │
       └───────────────────┼──────────────────┘
                           ▼
                       WorkerKit
                           │
                           ▼
                         SQLite
                           │
                optional projection
                           ▼
                         Hydra
```

That is the build.

---

# Define three execution profiles

This solves almost all the confusion.

## FAST

**Hard requirement: one top-level model request.**

```text
host gathers context
host retrieves memory
host performs cheap/free pre-processing

             ↓

ONE model request

             ↓

structured ActionBundle

             ↓

host executes
```

Pydantic:

```python
UsageLimits(request_limit=1)
```

Letta-fast:

```text
toolset.base = none
allowedTools = []
reasoningEffort = low
```

Then measure whether it actually stays at one provider request.

---

## BOUNDED

```text
max model requests = 2-3
```

Example:

```text
request 1 → patch
host → test

if failure:
request 2 → repair
host → test
```

This is probably your production sweet spot.

---

## AGENTIC

Full autonomous harness.

```text
Letta Code
Pydantic Coder
Hermes
etc.
```

Use when the problem genuinely requires adaptive exploration.

And **make the agent prove it was worth the extra inference**.

---

# How free-model orchestration should actually work

Your proposed Letta idea is good conceptually, but I would not implement it as:

```text
Letta
→ free model
→ Letta
→ free model
→ Letta
→ free model
→ Letta
```

That's exactly your latency problem.

Instead:

```text
                strong planner
                     │
               one model call
                     │
                     ▼
                  TaskGraph
                     │
          ┌──────────┼───────────┐
          ▼          ▼           ▼
       free A      free B      free C
          │          │           │
          └──────────┼───────────┘
                     │
              deterministic work
                     │
                     ▼
              optional final
               strong call
```

Pydantic's DynamicWorkflow is almost purpose-built for this and explicitly exists to avoid one orchestrator round-trip per delegated agent. ([GitHub][3])

So I would give `ComputeBroker`:

```python
class ComputePolicy:
    planner_model_class: str
    worker_model_class: str
    verifier_model_class: str

    max_strong_calls: int
    max_paid_usd: float

    free_quota_strategy: str
    escalation_threshold: float
```

And let LiveLLM resolve:

```text
"free coding model"
```

to whatever is economically correct **today**.

---

# Letta still has a very important role

I wouldn't abandon it.

The experiment I'm most interested in is:

```text
                   SAME TASK SET

Pydantic stateless
        vs
Pydantic persistent Memory
        vs
Letta persistent worker
```

Run 50 related tasks.

Ask:

```text
Does prior experience improve quality?

How many calls?

How many dollars?

How much latency?

How much useful information survives?

Does performance improve over run number?

Does Letta beat Pydantic memory?

By enough to matter?
```

If Letta shows:

```text
run 1 quality  .71
run 50 quality .89
```

while Pydantic stays:

```text
.72 → .75
```

then Letta is incredibly valuable.

If they both end up:

```text
~.87
```

but Pydantic costs 20% as much and runs 8× faster:

you learned something equally valuable.

**That's what MWGym is for.**

---

## I would change the wording in BIG-QUESTIONS

This:

> Letta does 5+ reasoning passes per turn. That's 5 API calls.

should become:

> We have observed 35–120s Letta turns. Streaming reasoning events are not equivalent to model requests, so MWGym must instrument provider-level requests. If the stripped no-tool Letta profile still requires multiple model invocations or materially higher latency than Pydantic/direct, Letta should be reserved for workloads where its persistence produces measured downstream gains.

And this:

> Pydantic AI or a simple SQLite memory might be 10x faster and 90% as effective.

should become a hypothesis:

```text
H1:
A PydanticAI worker with persistent memory
achieves ≥90% of Letta's held-out quality
at ≤30% of latency/cost.

H2:
Letta's cross-session persistence produces
statistically meaningful improvement on
related sequential tasks.

H3:
Strong planning + free execution recovers
≥90% of strong-only quality at ≤20% cash cost.
```

Now the repo isn't expressing frustration as architecture.

It's turning the frustration into experiments.

### The immediate build order

1. **MWGym becomes the only active lab codebase.**
2. Implement real `HarnessAdapter` for `direct`, `pydantic`, `letta`.
3. Add trustworthy provider-request telemetry.
4. Make SQLite canonical; Hydra async/optional.
5. Implement `FAST / BOUNDED / AGENTIC`.
6. Pydantic `FAST` uses `request_limit=1`.
7. Implement stripped `Letta FAST` and measure it.
8. Build real ComputeBroker + LiveLLM/Treasury.
9. Run **Free / Optimized / Ceiling** 15-task experiment.
10. Only then run **Pydantic-memory vs Letta-persistence**.

That will settle the Letta question empirically rather than having it derail the architecture. And it preserves the exciting part: if Letta genuinely does learn across real runs, you keep it precisely where that persistence earns its extra latency.

[1]: https://github.com/letta-ai/letta-agent-sdk/issues/233?utm_source=chatgpt.com "Docs: content's append-only delta semantics are undocumented after #227 · Issue #233 · letta-ai/letta-agent-sdk · GitHub"
[2]: https://github.com/letta-ai/letta-docs-md/blob/main/agent-sdk/quickstart/index.md "https://github.com/letta-ai/letta-docs-md/blob/main/agent-sdk/quickstart/index.md"
[3]: https://github.com/pydantic/pydantic-ai-harness/blob/main/README.md "pydantic-ai-harness/README.md at main · pydantic/pydantic-ai-harness · GitHub"
[4]: https://github.com/garrytan/gbrain?ref=zaharov.info "GitHub - garrytan/gbrain at zaharov.info · GitHub"
