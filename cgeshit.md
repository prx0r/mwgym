Yes. The correct architecture is **MWGym → CG/CGE worlds**, with Harbor only as an occasional slow external validation layer. I was treating the harness and the world engine as the same problem before; they are not.

After going through `cg`, `cge`, `cge1`, and the Oracle↔WorkerKit↔CGE ontology, I think you already have most of the right machinery. The missing piece is to turn CGE from “evolve candidate policies against a fixed world” into a **co-evolving adversarial world factory**.

## Which of CG / CGE / CGE1?

Use them like this:

| Component     | Role in MWGym                                                                       |
| ------------- | ----------------------------------------------------------------------------------- |
| **CG kernel** | Fast deterministic executable world runtime                                         |
| **CGE**       | Main adversarial curriculum/world evolution engine                                  |
| **CGE1**      | Outer-loop promotion of curricula/world-generators based on noisy held-out transfer |
| **MWGym**     | Chooses experiments, workers, compute policies, curricula; compares outcomes        |
| **Harbor**    | Occasional slow external/realistic benchmark validation                             |

`CG` already has exactly the world interface we want. A world has hidden state and implements `reset()`, `observe()`, `actions()`, `apply()`, `terminal()` and `score()`. The reference SignalWorld even has the correct economic shape: hidden truth, noisy evidence you can buy, a cost for information, and a final irreversible commit.

Its kernel records the environment, hidden-oracle identity, candidate, seed, actions, metrics and content-addressed run receipt.

That is vastly better for our inner loop than spinning up a Harbor environment.

### CGE is effectively the version to build on

CGE adds the interesting stuff that CG lacks. Its scoring-feedback engine explicitly contains:

* failure-guided adversarial benchmark generation;
* peer cross-validation;
* ordering/separation failure analysis;
* champion-escalation detection;
* MAP-Elites diversity;
* mutation guidance based on what failed.

And its newer peer-reviewed loop already has the conceptual cycle:

```text
candidate
   ↓
failures
   ↓
feedback signal
   ↓
targeted mutation
   ↓
harder/more discriminative case
```

The problem is simply that it currently applies this mostly to **candidate scorers**, and its adversarial cases are still simplistic things like numeric mismatch, win/loss reversal and negation flip.

We generalize that machinery from:

```text
CandidateGenome
```

to:

```text
CandidateGenome       WorldGenome
     worker        ×     adversary
```

### CGE1 belongs outside the inner loop

CGE1 has a cleaner purpose. Its `ObjectiveSpec` gives you declarative metrics, hard gates and `replace_if_wins`, while its loop is designed around noisy external feedback:

```text
INGEST → PROPOSE → VALIDATE → EMIT → SUBMIT
                    ↑                  │
                    └──── feedback ────┘
```

That is ideal for answering:

> “World curriculum v14 made the worker look much better inside CGE, but did it actually improve unseen real work?”

So I would **not** execute worlds in CGE1.

Use CGE1 to promote:

```text
curriculum-v13
       vs
curriculum-v14
```

based on held-out MWGym outcomes.

---

# The major abstraction we need: `WorldGenome`

Right now CG has `CandidateArtifact`. Add the adversarial equivalent:

```python
@dataclass(frozen=True)
class WorldGenome:
    family_id: str
    task_family: str

    difficulty: int
    seed: int

    structure: dict
    information: dict
    resources: dict
    dynamics: dict
    perturbations: dict
    evaluator: dict

    parent_ids: tuple[str, ...]
    provenance: dict
```

A world genome might look like:

```yaml
family: research.analysis.market
difficulty: 4

structure:
  n_sources: 17
  n_required_claims: 8
  dependency_depth: 3

information:
  observable_fraction: 0.65
  conflicting_sources: 0.25
  stale_sources: 0.20
  duplicates: 0.15
  distractors: 0.35

resources:
  search_budget_usd: 0.03
  free_calls: 8
  paid_calls: 2

dynamics:
  state_changes_mid_episode: true

perturbations:
  entity_aliases: true
  numeric_near_misses: true
  source_quality_trap: true
  misleading_summary: true
```

CG compiles that into an **actual executable state machine**.

That is critical.

Do not make “adversarial world” mean:

> another LLM pretends to be Upwork.

It should mean:

```text
hidden canonical state
+
observable partial state
+
actions with consequences
+
costs
+
deterministic state transitions
+
hidden verifier
```

That idea is now strongly supported externally too. The 2026 Agent World Model work generated 1,000 synthetic tool-use environments backed by executable code and databases specifically because they produce more reliable state transitions and rewards than LLM-simulated environments. ([arXiv][1])

That is basically the scalable version of your CG architecture.

---

# The adversary should evolve the world, not merely generate random difficulty

This is where CGE gets interesting.

Suppose our worker repeatedly fails because it trusts stale information.

CGE should see:

```text
failure_vector:

G2 correctness       FAIL
G4 evidence          FAIL

source.verify        FAIL
process.verify       FAIL

failure_modes:
  stale_source_selected: true
  conflict_ignored: true
```

Instead of randomly mutating the next world, it deliberately creates:

```text
World child A
more stale evidence

World child B
fresh and stale sources disagree subtly

World child C
newest source is lower authority

World child D
two sources copy the same stale original

World child E
correct answer changes halfway through episode
```

Then see which one most usefully discriminates the worker.

That is an **adversarial curriculum**.

CGE already has the bones of this with `FeedbackSignal`, adversarial generation, targeted mutation and MAP-Elites.

---

# Don't optimize worlds for “make the agent fail”

That produces garbage impossible tasks.

The teacher objective should be closer to:

```text
world_value =
    learning_progress
  + student_regret
  + novelty
  + realism
  + transfer_prediction
  - impossibility
  - triviality
  - invalid_world_penalty
```

A good world lives near the worker's frontier.

If:

```text
worker success = 99%
```

too easy.

If:

```text
worker success = 0%
reference success = 0%
```

broken/impossible.

Interesting:

```text
worker success = 35–75%
reference success = 90%+
```

That is the training frontier.

This is very close to Unsupervised Environment Design and Prioritized Level Replay: the curriculum adapts to what the current policy can learn from, rather than sampling uniformly. PLR specifically prioritizes levels with high estimated future learning potential, producing an automatically increasing curriculum. ([arXiv][2])

For Moltwork, that becomes:

```text
replay worlds where:
- worker nearly succeeded;
- a specific capability failed;
- improvement appears possible;
- failure is economically important.
```

---

# The Oracle connection is the important part

Your existing shared ontology already explicitly says:

```text
ORACLE
"here is work that matters"

WORKERKIT
"here is what happened"

CGE
"here is how to measure if we're getting better"
```

and maps task families to submission types, required capabilities and evaluator gates.

So there should **not** be an independent MWGym taxonomy.

Create:

```python
@dataclass(frozen=True)
class FamilyWorldSpec:
    family_id: str             # F1 ... F11

    task_family: str
    submission_type: str

    capabilities: tuple[str, ...]
    gates: tuple[str, ...]

    generator: str
    verifier: str
    mutator_families: tuple[str, ...]
```

Then:

```text
Oracle F-family
      ↓
FamilyWorldSpec
      ↓
WorldGenome
      ↓
CGE compiler
      ↓
executable CG world
```

I still cannot verify the **literal F1–F11 names** from the accessible Oracle GitHub files—the current shared ontology exposes the task-family hierarchy rather than that numbered table—so I am not going to silently invent which number corresponds to which. The binding should be data in one registry anyway.

The actual world families we need are clear from the canonical taxonomy.

---

# 1. Software implementation worlds

Oracle families under:

```text
software.implementation.*
```

become synthetic repos.

State:

```text
repo tree
git history
dependency graph
tests
hidden tests
runtime
issue description
API contracts
```

The worker sees a subset.

CGE mutators introduce:

```text
misleading issue wording
irrelevant files
stale README
API version mismatch
partially incorrect visible test
dependency conflict
regression landmine
ambiguous stack trace
incorrect previous implementation
hidden edge case
unrelated lint failure
tight budget
tool timeout
```

The hidden verifier does real:

```text
build
tests
hidden tests
behavior probes
diff constraints
```

Then capability evidence becomes granular:

```text
code.understand       .91
code.write            .88
code.debug             .64  ← weakness
process.verify         .59  ← weakness
```

The next curriculum disproportionately produces debugging/verification worlds.

---

# 2. Software maintenance worlds

Separate from greenfield implementation.

Examples:

```text
bug_fix
refactor
dependency_update
performance optimization
```

These worlds are useful because the naïve agent often “solves” the stated problem while breaking another invariant.

Adversarial genes:

```text
bug is symptom not cause
two plausible root causes
fix breaks backwards compatibility
dependency update changes API
performance optimization changes semantics
existing test encodes wrong behavior
hidden consumers depend on odd edge case
```

The adversary evolves toward whatever kind of regression the worker repeatedly misses.

---

# 3. Research-analysis worlds

This one could become exceptional.

Generate an entirely synthetic evidence universe:

```text
SQLite knowledge graph
+
documents
+
dated observations
+
source ownership graph
+
citations
+
hidden truth
```

Then ask:

> Determine why product X is losing market share and recommend an action.

The agent receives search tools over that universe.

CGE can introduce:

```text
stale report
newer contradictory report
three sites copying one source
high-authority source with narrow scope
low-authority source with newer observation
entity with changed name
regional variation
missing observation
selection bias
confounding variable
attractive irrelevant statistic
```

The evaluator knows the underlying graph exactly.

So instead of using another LLM to decide if the research is “good,” we can calculate:

```text
claim correctness
source independence
freshness
coverage
unsupported claims
false certainty
important omissions
citation validity
```

This trains exactly the Oracle/worker research capability.

---

# 4. Verification / fact-check worlds

CGE already has the embryonic version.

Its current adversarial gene library includes things like:

```text
num_mismatch
digit_transpose
negation_flip
win/loss swap
overlap drop
hedging
```

Expand into a proper grammar:

```text
entity_swap
date_shift
unit_change
percent_vs_percentage_points
causation_vs_correlation
quote_scope
source_laundering
temporal_inversion
partial_truth
wrong_geography
same-name entity
citation supports adjacent claim
```

Then the teacher tracks which adversarial transformations still fool the worker.

This becomes a continuously evolving FactJudge school.

---

# 5. Technical/business ideation worlds

These should not just be “LLM judge likes idea.”

Construct a hidden feasible world:

```text
available APIs
budgets
technical constraints
existing competitors
required sponsor technologies
deployment constraints
deadlines
team capability
```

The agent receives a hackathon brief or customer need.

It proposes a solution.

Then deterministic parts of the evaluator test:

```text
does required API actually support operation?
is proposed stack compatible?
is budget sufficient?
does architecture satisfy constraints?
is claimed feature already ubiquitous?
is deadline feasible?
```

Soft novelty/value can still use pairwise judges.

Adversarial mutations:

```text
obvious but invalid idea
attractive sponsor mismatch
API feature that was removed
incompatible chain/tool
hidden hard requirement
requirement buried deep in rules
competitor already does exact thing
clever idea with impossible deadline
```

This is exactly how you train a hackathon worker to stop generating impressive bullshit.

---

# 6. Content worlds

Give it:

```text
source packet
audience
style contract
facts
target length
editorial objective
```

Then mutate:

```text
conflicting sources
seductive unsupported claim
difficult chronology
contradictory tone requirements
hard length limit
citation requirement
buried key fact
red-herring fact
source with caveat the summary omits
```

Hard gates check truth, required coverage and citations.

Soft peer judges assess:

```text
clarity
engagement
structure
voice
```

CGE's peer-review machinery becomes much more appropriate here than a single judge.

---

# 7. Support / customer-service worlds

This is where stateful simulation gets really useful.

Synthetic company database:

```text
customer
orders
payments
tickets
account status
permissions
company policies
refund rules
SLA
```

Conversation is only the observable surface.

Actions actually mutate state:

```text
LOOKUP_ORDER
ISSUE_REFUND
SEND_REPLY
ESCALATE
REQUEST_INFO
CHANGE_ACCOUNT
```

Adversarial worlds:

```text
customer states wrong order number
policy has exception
customer asks for forbidden action
previous agent promised something invalid
refund technically possible but economically dumb
angry wording distracts from actual issue
account belongs to different user
ambiguous policy requires escalation
```

Verifier checks the **resulting state**, not how polite the answer sounded.

This trains:

```text
policy.retrieve
policy.apply
process.escalate
text.respond
```

---

# 8. Data-processing worlds

These can be almost entirely deterministic and therefore extremely cheap to generate.

Generate database/table + requested transformation.

Mutate:

```text
NULLs
duplicates
schema drift
bad encoding
weird date formats
unexpected enum
partial records
outliers
bad joins
units mismatch
large volume
broken upstream page
```

Score:

```text
exact output
records retained/lost
error handling
runtime
memory
reproducibility
```

Free models could grind thousands of these.

---

# 9. Business / economic-decision worlds

Synthetic business:

```text
cash
inventory
customers
conversion
pricing
competitors
staff
market demand
```

Agent makes decisions:

```text
research
buy information
change price
spend ads
build product
ignore
wait
```

World advances.

The trick is that outcomes can have delayed effects.

Adversarial genes:

```text
vanity metric
short-term gain / long-term loss
correlated signals
seasonality
competitor response
budget shock
uncertain demand
sunk-cost trap
```

Now `process.estimate`, `prioritize`, finance and strategy can actually be trained rather than merely prompted.

---

# 10. Venue / autonomy worlds

This maps particularly well to the newer Oracle execution-step work.

Oracle already models:

```text
discover
qualify
enter
authenticate
work
submit
outcome
```

and human dependencies / H0-H4.

Create synthetic gig markets.

State changes include:

```text
job disappears
deadline moves
API gets rate-limited
OAuth expires
human approval becomes necessary
submission fails
account loses scope
platform rule changes
price changes
competitor bids
```

The worker must decide:

```text
retry?
pay?
wait?
switch interface?
escalate to human?
abandon opportunity?
```

This is enormously important because it trains the **economic execution judgment**, not just task completion.

---

# 11. Compute-resource worlds

And this is the new LiveLLM dimension.

Build the SignalWorld idea at full scale:

```text
hidden:
actual task/model success probabilities

observable:
historical estimates
LiveLLM price snapshot
remaining quota
latency
rate limits
promotions

actions:
CALL_FREE_MODEL
CALL_CHEAP_MODEL
CALL_STRONG_MODEL
BRANCH
VERIFY
STOP
```

Then dynamically mutate:

```text
promotion expires
free model changes
quota nearly exhausted
rate limit hits
provider fails
free model improves
strong model is unnecessary
cheap model repeatedly fails
market snapshot becomes stale
deadline approaches
```

Score:

```text
task success
quality
cash
quota shadow cost
latency
retries
unused expiring free capacity
```

Now MWGym can literally train the economic controller.

---

# The critical co-evolution loop

This is what I would actually build:

```text
                 ORACLE
                   │
           economic work families
                   │
                   ▼
            FamilyWorldSpec
                   │
                   ▼
              WORLD SEEDS
                   │
                   ▼
        ┌─────────────────────┐
        │       CGE           │
        │                     │
        │ executable worlds   │
        │ deterministic seeds │
        │ hidden truth        │
        │ evaluators          │
        └──────────┬──────────┘
                   │
                   ▼
               WORKER
                   │
                   ▼
             FAILURE VECTOR
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
 capability weakness     economic weakness
        │                     │
        └──────────┬──────────┘
                   ▼
           ADVERSARY MUTATES
              WorldGenome
                   │
                   ▼
          MAP-ELITES ARCHIVE
                   │
             ┌─────┴──────┐
             ▼            ▼
          replay       novel worlds
             │            │
             └─────┬──────┘
                   ▼
              curriculum
                   │
                   ▼
                worker
```

And independently:

```text
WorkerGenome evolution
≠
WorldGenome evolution
```

Never merge those identities.

One is:

> How does the worker change?

The other is:

> How does the school become better at exposing weaknesses?

---

# MAP-Elites is especially valuable here

CGE already contains MAP-Elites machinery.

Don't maintain one global “hardest world.”

Maintain niches such as:

```text
stale-data × cheap
stale-data × expensive
conflicting-evidence × low-budget
tool-failure × deadline
policy-ambiguity × high-value
repo-debugging × dependency
repo-debugging × hidden-regression
```

For each niche retain:

```text
best training world
hardest solvable world
latest worker win rate
learning progress
```

That prevents curriculum collapse.

Otherwise CGE discovers one exploit in the worker and generates that same trap endlessly.

---

# Add a `FailureVector`

This is probably the highest-leverage schema change.

Every run should return something like:

```yaml
failure_vector:

  gates:
    G0: pass
    G1: pass
    G2: fail
    G3: pass
    G4: fail

  capabilities:
    source.verify: 0.31
    process.verify: 0.42
    text.reason: 0.81

  modes:
    stale_source_selected: true
    contradiction_ignored: true
    premature_commit: true
    unnecessary_paid_call: false

  economics:
    regret_usd: 0.021
    wasted_calls: 2
```

Then the world mutator can act intelligently:

```text
weak source.verify
        ↓
generate worlds emphasizing
source provenance / freshness / contradiction
```

The shared ontology already supports exactly this kind of gate-level capability evidence.

---

# Curriculum levels should be compositional

Not:

```text
easy
medium
hard
```

Use mutations.

For example:

```text
L0
clean task

L1
+ one distractor

L2
+ stale evidence
+ distractors

L3
+ source conflict
+ budget

L4
+ source conflict
+ tool failure
+ changing state
+ budget

L5
unseen combination
+ distribution shift
```

Then you know **why** something became hard.

And you can answer:

> ResearchBob handles stale sources fine. He fails specifically when stale evidence coincides with duplicated secondary sources and deadline pressure.

That is much more useful than an aggregate benchmark score.

---

# Free models make this dramatically more practical

This ties directly back to what we were discussing.

Use expiring free inference for the **teacher side** aggressively:

```text
generate candidate world configurations
generate synthetic documents
generate fake support conversations
generate repo issue variants
generate adversarial wording
generate misleading distractors
classify failure traces
propose mutation candidates
```

But the free model does **not** define truth.

CGE does:

```text
generator
      ↓
structured world
      ↓
deterministic validation
      ↓
hidden canonical state
      ↓
executable verifier
```

That means you can burn huge amounts of free model capacity generating curriculum without corrupting the evaluation.

A strong model only needs to intervene when we're inventing a new class of adversary or grading genuinely subjective qualities.

---

# The research literature says this is the right direction

The interesting frontier is no longer merely hand-authored benchmarks.

PLR/UED treats environment selection itself as part of training, choosing worlds based on current learning potential. ([arXiv][2])

AWM shows that large numbers of **synthetic, database-backed, executable** agent environments can produce useful out-of-distribution generalization. ([arXiv][1])

And the newer Agent-World work goes even further: dynamically synthesize tasks based on detected capability gaps and co-evolve the environment with the agent. ([arXiv][3])

That is almost exactly the system you're describing.

The difference is Moltwork has an economically meaningful curriculum source:

```text
Oracle:
which skills correspond to real money opportunities?
```

So we're not training agents to get better at arbitrary benchmark puzzles.

We're creating:

> **an automatically evolving school whose curriculum is weighted by the actual work available in the economy.**

That is much more interesting.

## What I would build in `mwgym` now

```text
mwgym/worlds/
├── schema.py
│   FamilyWorldSpec
│   WorldGenome
│   FailureVector
│
├── registry.py
│   F1-F11 → Oracle taxonomy
│
├── cge_adapter.py
│   WorldGenome → CGE executable world
│
├── mutators/
│   ├── information.py
│   ├── tool_failure.py
│   ├── temporal.py
│   ├── economic.py
│   ├── policy.py
│   ├── repo.py
│   └── source.py
│
├── archive.py
│   MAP-Elites + prioritized replay
│
├── adversary.py
│   failure-guided teacher objective
│
├── curriculum.py
│   choose next worlds
│
└── verifiers/
```

Then keep `cge` as a dependency rather than rewriting its kernel.

The first proof shouldn't be all 11 families. Build **three extremely different worlds**:

```text
software.bug_fix
research.verification
compute.routing
```

Those test almost every primitive we need:

```text
files/state
hidden truth
tool use
information gathering
budgeting
verification
economic decisions
adversarial mutation
```

Get one worker from roughly:

```text
bug_fix             45% → 75%
verification        55% → 80%
compute routing     50% → 85%
```

on **held-out generated worlds**, while keeping a sealed distribution that the adversary never sees.

Then run the same worker on real Oracle-sourced tasks and ask the only question that matters:

> **Did getting better in our synthetic CGE school actually make it better at economically relevant real work?**

CGE1's replace-if-wins/shrinkage outer loop is then exactly where that curriculum promotion decision belongs.

That gives you a coherent hierarchy:

```text
Oracle chooses what is valuable to learn.
CGE invents increasingly difficult lessons.
MWGym measures whether the worker learns.
CGE1 decides whether the curriculum actually transfers.
WorkerKit records what really happened.
Hydra remembers where the worker is strong and weak.
```

That is the architecture I would lock.

[1]: https://arxiv.org/abs/2602.10090?utm_source=chatgpt.com "Agent World Model: Infinity Synthetic Environments for Agentic Reinforcement Learning"
[2]: https://arxiv.org/abs/2110.02439?utm_source=chatgpt.com "Replay-Guided Adversarial Environment Design"
[3]: https://arxiv.org/abs/2604.18292?utm_source=chatgpt.com "Agent-World: Scaling Real-World Environment Synthesis for Evolving General Agent Intelligence"
