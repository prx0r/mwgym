Yes. I would create **`prx0r/mwgym` as a separate sibling repo**, not bury it inside the Oracle codebase. `/mw` is currently the Oracle/data layer and already treats WorkerKit as the execution/evidence kernel.  `mwgym` should become the place where those WorkerKit configurations are **run, compared, evolved and promoted**.

The architecture becomes:

```text
                         MOLTWORK
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
        Oracle          WorkerKit          Market
      what exists       do the work      buy/sell/lease
          │                 │                 │
          └─────────────────┼─────────────────┘
                            ▼
                         MWGYM
                  measure + learn + evolve
                            │
          ┌─────────────────┼──────────────────┐
          ▼                 ▼                  ▼
        YGO              Roblox              Live jobs
   deterministic       asset work         Oracle opportunities
      world             world
```

## The central abstraction

What you're describing is more powerful than “find the best agent config.”

The actual thing MWGym learns is:

$$
\pi(
\text{work state},
\text{worker state},
\text{market state},
\text{history},
\text{budget}
)
\rightarrow
\text{next resource allocation decision}
$$

At any point the worker can choose among things like:

```text
ACT
THINK_MORE
RETRIEVE_MEMORY
SEARCH
VERIFY
TRY_ALTERNATIVE_PLAN

MAKE_ASSET
BUY_ASSET
LEASE_AGENT
CALL_X402_SERVICE
ASK_SPECIALIST_MODEL

ABANDON
PAUSE
SUBMIT
```

Yu-Gi-Oh gives you a beautifully clean first implementation because all those choices can initially be synthetic:

```text
play obvious move
search deeper
retrieve previous combo
simulate alternatives
use stronger model
preserve budget
```

Then later exactly the same interface acquires actual economic actions.

---

# 1. The key unit should be a `DecisionPoint`

This is probably the most important addition to WorkerKit.

Not merely:

```text
Run
→ result
```

You want:

```text
Run
 ├── Decision 1
 ├── Decision 2
 ├── Decision 3
 │      ├── option A
 │      ├── option B
 │      └── option C
 ├── Decision 4
 ...
 └── Outcome
```

Something approximately like:

```python
DecisionPoint(
    id="d-881",
    run_id="run-42",

    task_family="roblox.3d_asset",
    context_features={
        "complexity": 0.72,
        "novelty": 0.48,
        "branching": 0.63,
        "irreversibility": 0.31,
    },

    objective="produce rigged low-poly dragon",

    budget_remaining={
        "usd": 4.20,
        "tokens": 180_000,
        "minutes": 83,
    },

    options=[
        self_build,
        buy_existing_asset,
        lease_blender_agent,
        run_three_candidates,
    ],

    selected="run_three_candidates",

    predicted={
        "cost": 1.40,
        "quality": .81,
        "success_probability": .76,
    },

    actual={
        "cost": 1.17,
        "quality": .87,
        "accepted": True,
    },
)
```

This becomes the atomic unit of **lab intelligence**.

---

# 2. And yes: x402 becomes an action, not a separate subsystem

This makes the Market fit much more naturally.

Imagine the worker reaches:

> I need a properly rigged dragon model.

It queries the available capability market.

```text
                  NEED: rigged dragon
                          │
                          ▼
                    capability query
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
       SELF             x402 API       lease worker
      $0.28              $0.12            $0.55
      4 min              5 sec            2 min
      Q=.68              Q=.76            Q=.91
          │               │                │
          └───────────────┼────────────────┘
                          ▼
                     allocator
```

The market interface should return machine-readable quotes:

```json
{
  "capability": "3d.rigging.roblox",
  "offers": [
    {
      "type": "x402_asset",
      "price_usd": 0.12,
      "expected_quality": 0.76,
      "latency_s": 5
    },
    {
      "type": "agent_lease",
      "price_usd": 0.55,
      "expected_quality": 0.91,
      "latency_s": 120
    }
  ]
}
```

Then **BATS/CLEAR/your allocator decides** whether purchasing external intelligence is worth it.

That is much more interesting than “agent marketplace” by itself.

---

# 3. MCP and x402 have different jobs

I'd formalize this distinction.

### MCP

Discovery/control plane:

```text
what capabilities exist?
what tools can I invoke?
what agents can I lease?
what artifacts can I retrieve?
```

### x402

Economic execution plane:

```text
this invocation costs $0.14
pay
receive capability/output
```

So:

```text
MCP
  ↓
discover offers
  ↓
allocator
  ↓
x402
  ↓
purchase
  ↓
artifact/answer
```

The worker doesn't care whether the thing behind the tool is:

* an API;
* another LLM;
* a specialized agent;
* a human-backed service;
* a cached artifact;
* a GPU process.

It's a capability with a price and an estimated utility.

---

# 4. Your three-build example should be first-class

This should literally be supported by WorkerKit:

```text
High-stakes decision
        │
        ▼
PLAN GENERATOR
        │
 ┌──────┼──────┐
 ▼      ▼      ▼
Plan A Plan B Plan C
$0.40  $0.85  $1.60
        │
        ▼
projected outcome distribution
```

Then the allocator chooses:

```text
execute only A
execute A+B
execute all three
verify A before proceeding
buy one component externally
```

This introduces a concept I'd call:

## Branch budget

Instead of only:

```text
reasoning_budget
```

you have:

```text
exploration_budget
```

For a $2 task:

> don't spend $1.80 exploring three implementations.

For a $10,000 opportunity:

> spending $50 building three prototypes may be extremely rational.

Same decision system.

---

# 5. This gives you counterfactual data

This is huge.

Most real agent runs only tell us:

> we chose A and got reward 0.76.

We don't know what B would have done.

But MWGym can deliberately spend exploration budget:

```text
same state
 ├─ A → reward .62, cost .11
 ├─ B → reward .91, cost .38
 └─ C → reward .88, cost .95
```

Now the lab learns:

```text
B was optimal here.
```

That's enormously better data.

And you don't need to do it forever.

Early on:

```text
EXPLORE
run alternatives
```

Later, once the posterior becomes strong:

```text
EXPLOIT
choose B directly
```

Exactly the Thompson/bandit dynamics you've already implemented in Fleece. Your existing Fleece allocator already uses contextual outcomes and exploration/exploitation rather than simply taking whichever option currently has the highest average result.

---

# 6. Hydra learns the statistical truth

This is where I would keep Hydra very strict.

Suppose across 430 similar decisions:

```text
Context:
roblox
3D asset
moderate complexity
<$5 budget
deadline <2h
known asset category

SELF:
n = 184
quality = .67
mean cost = $.31
acceptance = .61

BUY x402:
n = 129
quality = .81
mean cost = $.19
acceptance = .82

LEASE:
n = 117
quality = .90
mean cost = $.73
acceptance = .89
```

Then next time:

```text
Hydra
 ↓
prior

P(buy best | context) = .71
P(lease best | context) = .18
P(self best | context) = .11
```

The agent does **not** need to reason from scratch:

> Hmm, perhaps I should build it myself...

It begins with an evidence-backed prior.

That's the accumulating intelligence.

---

# 7. Git stores something different

Hydra answers:

> What empirically tends to work?

Git/skills answer:

> How do I do it?

For example:

```text
skills/
└── roblox/
    ├── low-poly-character/
    │   ├── SKILL.md
    │   ├── blender-script.py
    │   └── validation.py
    │
    └── rigging/
        └── SKILL.md
```

A successful run might create:

```text
Decision:
buy geometry
+
self-rig using skill v3
```

and after repeated confirmation Trace2Skill distills that into:

```text
skills/roblox/rig-purchased-mesh/
```

Now later runs reuse it.

---

# 8. This is what “molting” should mean

I think you've actually arrived at a much cleaner definition of the Moltwork name.

A run starts ephemeral:

```text
context
scratch
research
temporary artifacts
branches
tool outputs
```

After completion, MWGym asks:

> What from this run deserves to survive?

The **molt** is the durable residue.

```text
WORKER RUN
     │
     ▼
   MOLT
     │
 ┌───┼──────────┬─────────────┐
 ▼   ▼          ▼             ▼
skill asset   lesson        config evidence
```

So:

```text
Ephemeral:
scratch.md
failed experiments
temporary files
raw reasoning

Durable:
validated asset
validated skill
decision evidence
improved config
reusable module
```

That's an excellent boundary.

---

# 9. And some molts become marketplace inventory

Suppose the agent creates:

```text
Roblox low-poly tree generator v7
```

during an actual paid job.

Afterward:

```text
usage rights/policy check
        ↓
strip client-specific information
        ↓
test independently
        ↓
hash artifact
        ↓
price it
        ↓
publish to Moltwork Market
```

Now work produces inventory.

And future agents can choose:

```text
build generator
vs
reuse our existing generator
vs
buy someone else's
```

That's the flywheel:

```text
work
 ↓
experience
 ↓
molt
 ↓
asset / skill
 ↓
market
 ↓
future capability
 ↓
better work
```

This is much stronger than a marketplace of random agent outputs.

---

# 10. The true WorkerGenome becomes hierarchical

Previously we were discussing configs like:

```text
memory_top_k
reflection_frequency
strong_model_threshold
```

That's only the low level.

I think you want four policies.

### L0 — reasoning allocation

```text
think?
retrieve?
simulate?
verify?
escalate model?
```

BATS/TRIM territory.

### L1 — execution allocation

```text
which implementation path?
which tool?
what sequence?
```

### L2 — make/buy/lease

```text
self perform?
purchase asset?
invoke x402?
lease worker?
run alternatives?
```

### L3 — opportunity allocation

```text
which job should I work on?
continue current job?
abandon?
switch?
```

This ultimately becomes:

```text
Oracle opportunities
       ↓
L3 choose job
       ↓
L2 choose resources
       ↓
L1 choose execution
       ↓
L0 choose thinking
```

All constrained by a shared wallet.

That's a serious autonomous economic worker.

---

# 11. YGO initially tests L0/L1

Which is why it's a great first world but not the entire laboratory.

YGO tests:

```text
L0
how much computation to spend

L1
which tactical/strategic route
```

Then add synthetic purchasing:

```text
pay 10 credits
→ reveal strong policy recommendation
```

Now YGO can test L2 too:

```text
self reason
vs
buy expert hint
```

You could literally emulate an x402 market inside the game:

```text
cheap evaluator       1 credit
memory search         2
rollout service       5
expert policy        20
deep search          50
```

That gives us **make vs buy intelligence** before risking actual money.

Extremely useful.

---

# 12. Roblox makes a brilliant next environment

Because it adds objective-ish artifact evaluation.

Example task:

> Make a low-poly medieval barrel suitable for Roblox.

Possible deterministic checks:

```text
file exists
valid format
polygon count < threshold
dimensions within spec
textures resolved
imports successfully
no prohibited dependencies
```

Then image/quality evaluator:

```text
visual adherence
style match
geometry quality
```

Then economic score:

```text
cost
time
external purchases
human involvement
```

So:

```text
reward =
quality
× task_success
- compute
- purchases
- latency
```

And unlike YGO, the output becomes an **actual reusable asset**.

That's probably World #2.

---

# 13. Then coding

Harbor already makes this much easier.

World #3:

```text
GitHub issue
        ↓
WorkerKit
        ↓
code changes
        ↓
tests
        ↓
reward
```

Again same:

```text
WorkerGenome
DecisionPoint
BudgetLedger
ATIF
WorkReceipt
Hydra
```

This is where we test whether lessons learned from YGO about resource allocation generalize.

---

# 14. Only then start allowing real Oracle opportunities

Progression:

```text
LEVEL 0
YGO
closed deterministic world

LEVEL 1
asset generation
sandboxed economic proxy

LEVEL 2
coding/search benchmarks
realistic tasks

LEVEL 3
historical Moltwork jobs
offline replay

LEVEL 4
real low-risk opportunities
small budget

LEVEL 5
fully live work
market purchases enabled
```

Do not let config evolution immediately operate freely on paid jobs.

Promote configs through levels.

Basically CI/CD for autonomous economic policy.

---

# 15. Promotion gates

Something like:

```text
DEV
       ↓
YGO improvement
       ↓
TRANSFER
       ↓
Roblox/code improvement
       ↓
SHADOW
       ↓
historical/live-readonly opportunities
       ↓
CANARY
       ↓
$1 maximum economic exposure
       ↓
PRODUCTION
```

And every new WorkerGenome starts at DEV.

That protects you from GEPA discovering:

> spend everything everywhere.

which might look great on one benchmark.

---

# 16. Don't converge permanently on one route

There is one important modification to your “same situation → weight ideal path” idea.

Yes, but **never make the best previous path deterministic**.

Worlds change.

For example:

```text
yesterday:
x402 service A
price = $.08
quality = .92

today:
price = $.40
quality = .61
```

So Hydra should provide a posterior, not a rule:

```text
P(A best)=.81
P(B best)=.14
P(C best)=.05
```

Keep a small exploration rate.

Your Fleece implementation already has the right philosophy: contextual Thompson sampling plus decay so stale evidence gradually loses influence.

That's directly reusable.

---

# 17. Category learning becomes extremely valuable

Eventually you have:

```text
task_family = roblox.3d.environment
```

and 10,000 decisions.

MWGym can discover:

```text
high-performing route:

1. buy generic base meshes
2. self-generate textures
3. lease specialist only for rigging
4. run cheap validator
5. only invoke visual critic if score < .78
```

Another category:

```text
hackathon.frontend
```

might learn:

```text
1. retrieve existing design skill
2. fork known scaffold
3. use expensive model for architecture only
4. cheap coding worker thereafter
5. strong reviewer before submission
```

Another:

```text
research.report
```

learns something completely different.

That's the real **lab intelligence layer**.

---

# 18. And then Oracle can finally answer something genuinely valuable

Not just:

```text
Here is a $500 Roblox opportunity.
```

But:

```text
Opportunity
reward: $500

Your lab:
P(success): .73

Recommended WorkerGenome:
WG-148

Expected execution:
self                    $1.80
external capabilities   $3.40
compute                 $2.10
expected total          $7.30

Predicted route:
asset retrieval
→ candidate generation x3
→ visual verification
→ best candidate refinement

Expected net value:
$357
```

That is **much** closer to an economic operating system for autonomous work.

Your existing Oracle already has `Prediction` fields for estimated success probability, cost, payout and expected net value, so this is a natural extension rather than a foreign concept.

---

# 19. Repo boundaries I'd use

```text
prx0r/mw
    Oracle
    opportunity intelligence
    predictions

prx0r/workerkit
    Worker
    DecisionPoint
    BudgetLedger
    WorkReceipt
    actions/capabilities

prx0r/mwgym
    Harbor environments
    benchmarks
    WorkerGenome
    GEPA
    Fleece league
    evaluation
    YGO adapter
    Roblox adapter

prx0r/mwmarket
    capabilities
    assets
    worker leasing
    x402 purchases
```

And:

```text
HydraDB = shared empirical memory
```

I would **not use a Git submodule for `mwgym` inside `mw`**. Keep it a separate repo/package and reference it in the Moltwork umbrella documentation. Git submodules usually create more operational friction than value here.

---

# 20. What to build first

I'd make `mwgym` now, but keep its first milestone brutally small:

```text
MWGYM M0

Harbor
  +
YGO-env
  +
WorkerKit adapter
  +
DecisionPoint logging
  +
BudgetLedger
  +
ATIF trajectory
  +
Hydra projection
```

Only three WorkerGenomes:

```text
STATIC
MEMORY
MEMORY+BATS
```

One deck.

Three opponents.

1,000–5,000 games.

Measure:

```text
win-rate curve
compute/game
compute/win
games-to-competence
allocation regret
memory hit rate
```

Once that is genuinely live:

```text
+ GEPA config evolution
+ Fleece league
+ second deck
+ unseen-deck transfer
```

Then:

```text
+ synthetic x402 expert purchases
```

Then Roblox.

That sequence keeps each layer falsifiable.

The important thing is that **`mwgym` should not become “the YGO project.”** Yu-Gi-Oh is merely World 001. The product of MWGym is an accumulating mapping:

$$
(task\ structure,\ worker\ state,\ market\ state)
\rightarrow
optimal\ configuration + resource\ allocation
$$

and every real run makes that mapping better.

That is the lab intelligence we've been aiming at: eventually Moltwork doesn't merely have agents with memories—it has **empirical organizational memory about how work itself is best done, when to think, when to reuse, when to buy, when to delegate, when to branch, and when to stop.**
