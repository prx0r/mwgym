Yes. The **fresh Git workspace + persistent Letta agent + Git-backed Letta memory** design is still the strongest foundation. The refinement is to stop asking Letta to be the entire system.

The right build is:

> **Letta = persistent cognitive organism.
> Git = mutable/versioned substrate.
> Moltwork = economic + evolutionary nervous system around it.**

That actually lines up unusually well with where Letta itself has gone in 2026. Their Context Repositories are Git-backed; memory subagents already operate in isolated Git worktrees and merge learned changes back; Letta Mods now expose the harness itself as something an agent can learn and modify. ([Letta][1])

And their August Agents SDK explicitly pushes the same separation we want: a persistent agent can retain identity/memory while programs handle fixed control flow, concurrency, external events, and workflows across different models and machines. ([Letta][2])

So I would **not build a replacement for Letta**.

I would build a specialized **economic meta-harness around Letta**.

---

# The architecture

```text
                      MOLTWORK
              economic/evolutionary layer
                          │
          ┌───────────────┼──────────────────┐
          │               │                  │
       ORACLE           MWGYM               QDW
    what pays?        what learns?       what resource?
          │               │                  │
          └───────────────┼──────────────────┘
                          │
                    CAMPAIGN ENGINE
                          │
            WorkOrder + SuccessModel
                          │
                          ▼
                 FRESH GIT WORKSPACE
                          │
                    base commit B0
                          │
                          ▼
                    LETTA WORKER
                 persistent identity
                 persistent MemFS
                 persistent Skills
                 persistent experience
                          │
                 fresh conversation
                          │
                works inside Git repo
                          │
         ┌────────────────┼─────────────────┐
         │                │                 │
       direct          delegate           verify
       work              work               work
                          │
                          ▼
                    COMPUTE BROKER
                          │
              LiveLLM + Treasury + BATS
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
           FREE          CHEAP       STRONG
           model         model       model
             │
      Pydantic/direct/
      stateless Letta
             │
             └────────────┬────────────┘
                          ▼
                    LETTA SYNTHESIS
                          │
                          ▼
                   final Git commit
                          │
                       B0 → B1
                          │
                     verifier
                          │
                   WorkerKit receipt
                          │
               ┌──────────┴─────────┐
               ▼                    ▼
             HYDRA                CGE
      empirical experience   adversarial school
               │                    │
               └──────────┬─────────┘
                          ▼
                     EVOLUTION
          memory / skill / mod / process
                    proposals
                          │
                    Git worktrees
                          │
                held-out MWGym eval
                          │
                   promote / reject
```

That is the stack.

---

# There are actually three different Git layers

This distinction makes the design much cleaner.

### 1. Work Git

Every task gets an isolated Git state.

For a synthetic CGE world:

```text
/runs/R9182/
    git init
    ↓
world-generated files
    ↓
git commit "world: initial state"
    ↓
LETTA works
    ↓
git commit "worker: solution"
```

For an existing codebase:

```text
canonical repository
        │
       SHA X
        │
 git worktree add
        │
        ▼
/runs/R9182/
```

So every run has:

```yaml
workspace:
  base_commit: abc123
  final_commit: def456
  diff_digest: ...
```

You can reproduce exactly what the worker encountered and exactly what it changed.

---

### 2. Letta Memory Git

This is separate.

Letta's current memory model already does this. MemFS is a Git repository owned by the agent, with `system/` always loaded and other files progressively disclosed. ([Letta][3])

Example:

```text
Researcher-v7 MemFS

system/
  identity.md
  operating-principles.md

domains/
  hackathons.md
  software-debugging.md
  research.md

failures/
  verification.md

skills/
  requirement-matrix/SKILL.md
  source-audit/SKILL.md
  repo-debug/SKILL.md
```

That repo persists while task repos come and go.

This is **the worker's learned brain**.

---

### 3. Moltwork genome/config Git

Keep economic and experimental machinery independently versioned:

```text
workers/
  researcher.yaml

processes/
  coding.yaml
  research.yaml

compute/
  bats-v3.yaml

evaluators/
  technical-implementation-v7.yaml

worlds/
  software-bugfix-v12.yaml
```

This is what MWGym/CGE evolves.

Do not dump all of this into Letta memory.

---

# The critical identity model

A `WorkerVersion` should mostly consist of references.

```yaml
worker_version: researcher-v17

letta:
  agent_id: agent-a18...
  memfs_commit: 82f88a...
  trajectory_schema: letta-trajectory-v1

cognition:
  system_commit: ...
  skills_commit: ...
  mods_commit: ...
  process_policy: process-research-v8

parent:
  researcher-v16
```

The important point:

**the model isn't the worker.**

You can take:

```text
Researcher-v17
```

and run it with:

```text
MiMo
GLM
Claude
GPT
Kimi
```

while keeping its accumulated experience.

That's exactly the direction Letta is pursuing: identity and memory persist across models and machines. ([Letta][2])

---

# ComputePolicy is NOT part of WorkerVersion

This remains an important distinction from our earlier design.

```text
WorkerGenome
────────────
memory
skills
mods
instructions
planning policy
verification habits

ComputePolicy
─────────────
model routing
free quota strategy
branching
escalation
parallelism
budget thresholds

MarketSnapshot
──────────────
prices
promotions
free models
limits

TreasurySnapshot
────────────────
our credits
quotas
balances
expiry
```

Therefore:

```text
Researcher-v17
+
ComputePolicy BATS-v4
+
MarketSnapshot 2026-09-01T05:00
+
TreasurySnapshot X
=
one WorkerRun
```

Cloudflare changing its free allocation does **not** create `Researcher-v18`.

---

# Where Pydantic belongs

I would now put Pydantic **under Letta rather than beside it** for many workloads.

Not:

```text
Letta OR Pydantic
```

but:

```text
                 Letta
             persistent brain
                   │
             mw_delegate()
                   │
                   ▼
           Moltwork Executor
        ┌─────────┼──────────┐
        ▼         ▼          ▼
      direct   Pydantic   stateless
       LLM       agent      Letta
```

Pydantic has an extremely useful property for us: hard `UsageLimits` covering `request_limit`, monetary cost, tokens and tool calls, including across multi-agent delegation. ([Pydantic][4])

That makes it ideal for:

```text
"do this with ONE call"

"max 3 calls"

"max $0.004"

"max 4 tool calls"
```

Those are **economic execution primitives**, not identity/memory primitives.

So a Pydantic worker node could be:

```python
cheap_worker.run(
    subtask,
    model=broker.selected_model,
    usage_limits=UsageLimits(
        request_limit=1,
        cost_limit=Decimal("0.002"),
    )
)
```

Then return its artifact to the persistent Letta agent.

This gets us the best of both worlds.

---

# This also solves the Letta latency problem

Don't do:

```text
Letta thinks
↓
tool
↓
Letta thinks
↓
cheap LLM
↓
Letta thinks
↓
tool
↓
Letta thinks
```

for every trivial operation.

Use:

```text
LE TTA

one strategic planning phase
        │
        ▼
     TaskGraph
        │
 ┌──────┼───────┬───────┐
 ▼      ▼       ▼       ▼
FREE   FREE    FREE    CHEAP
one    one     one      one
call   call    call     call
 │      │       │        │
 └──────┴───────┴────────┘
               │
               ▼
          artifacts/files
               │
               ▼
            LETTA
      decision/synthesis
```

So expensive persistent cognition happens around the places where it matters.

---

# Letta should own strategic cognition

I would reserve the stateful Letta worker for decisions such as:

```text
What is the task actually asking?

What have I learned previously?

Which prior strategy applies?

How should this problem be decomposed?

What information am I missing?

Did these cheap workers collectively answer it?

Is the current approach failing?

Do I change strategy?

What lesson should I retain?
```

The cheap executors do:

```text
extract these 20 requirements
classify these records
search these five queries
implement these boilerplate files
produce five alternatives
run these transformations
summarize this document
test this hypothesis
```

That's a much saner compute hierarchy.

---

# BATS becomes much more powerful in our version

Your current `providers/bats.py` is basically a placeholder:

```text
uncertainty > .7 → Groq
tiny budget → MiMo
otherwise → MiMo
```

And `broker.py` still has hand-written quality numbers such as `.7`, `.8`, `.95`.

Don't throw BATS away. Generalize it.

The actual BATS research result is useful: merely giving an agent more tool calls does not scale well; exposing the remaining budget and dynamically deciding whether to **dig deeper or pivot** improves cost-performance scaling. ([arXiv][5])

Our BATS should therefore operate on a `DecisionPoint`:

```yaml
decision:
  task_family: research.analysis
  stage: verify
  current_quality: 0.74
  uncertainty: 0.31

budget:
  cash_remaining: 0.083
  strong_calls_remaining: 1

free:
  glm_flash_remaining: 9300_neurons
  mimo_remaining: unlimited
  reset_in: 4h12m

history:
  researcher-v17:
    research.verify:
      glm_flash:
        success: 0.79
        n: 83
      strong:
        success: 0.94
        n: 31
```

Then choose:

```text
CONTINUE_FREE
BRANCH_FREE
VERIFY_FREE
BUY_CHEAP
ESCALATE_STRONG
SWITCH_PROVIDER
ASK_HUMAN
STOP
ABORT
```

This is more interesting than model routing.

It's **economic cognition allocation**.

---

# Hydra supplies the posterior

Never hardcode:

```text
GLM quality = .80
Claude quality = .95
```

Instead Hydra learns:

```text
Researcher-v17
+
research.analysis.market
+
stage=source_verify
+
GLM-4.7-flash

n=134
pass=.86
median cost=$0
median latency=1.8s
escalation-after=.09
```

versus:

```text
Researcher-v17
+
software.debug
+
GLM-4.7-flash

n=48
pass=.52
```

Now the economics becomes worker-specific.

That's your moat.

---

# Hydra and Letta memory are fundamentally different

This distinction should remain rigid.

### Letta asks:

> What should **I remember** to work better?

### Hydra asks:

> What has **empirically happened** across runs?

Hydra contains:

```text
WorkerVersion
TaskFamily
World
Process
Skill
Model
Provider
RouteDecision
Evaluator
FailureVector
Artifact
Outcome
Cost
```

Letta should not be expected to memorize:

```text
GLM source-verification success = .8124
```

Moltwork retrieves the relevant statistical summary and gives it a `LabBrief`.

Likewise Hydra should not try to replace:

```text
"Before designing a hackathon entry,
construct an explicit requirements matrix."
```

That belongs in Letta Skill/Memory.

---

# The current Letta runtime has one important wrong switch

Your design document is correct:

> persistent agent + **fresh conversation per WorkOrder**.

But current `services/runtime-letta/src/index.ts` runs jobs using:

```ts
stateless: true
```

and even comments:

> “skip memory for single-shot tasks”

and “stateless skips MemFS sync, skills, mods, transcript writes.”

That should **not be your production treatment**.

It should become an experiment arm:

```text
LE TTA_STATEFUL
persistent memory + fresh conversation

LE TTA_STATELESS
same harness, no memory

DIRECT
single raw model

PYDANTIC_BOUNDED
controlled micro-agent
```

In fact, the Letta Agent SDK only added explicit stateless sessions in v0.7.0 in August. ([GitHub][6])

That's perfect for MWGym.

You now have a clean memory ablation built into the same harness.

---

# Git makes the evolutionary part extremely elegant

After a run:

```text
Worker v17
MemFS @ A

Task branch
B0 ─────────→ B1

Outcome:
score=.71
failure=missed_requirement
```

Reflection generates:

```text
candidate learning:
"Before implementation, extract acceptance requirements."

proposed change:

MemFS:
A ─────────→ A'
```

But **do not apply A' to the production worker**.

Instead:

```text
MemFS main
    A
    │
    ├──── worktree candidate-182
    │              │
    │              ▼
    │             A'
    │
    └──── incumbent
                   A
```

MWGym now runs:

```text
             SAME HELD-OUT WORLDS

A / incumbent               A' / candidate
      │                          │
      ▼                          ▼
    score                      score
```

CGE/CGE1 determines promotion.

If candidate wins:

```text
git merge candidate-182
```

Now:

```text
Researcher-v17 → Researcher-v18
```

If not:

```text
git branch -D candidate-182
```

but its failure stays in Hydra.

This is an exceptionally clean learning architecture.

And importantly, Letta itself now uses this exact kind of Git-worktree pattern for concurrent memory subagents. ([Letta][1])

---

# Evolution should happen on four surfaces

This is where the custom build becomes worthwhile.

| Surface         | Example mutation                           | Optimizer                 |
| --------------- | ------------------------------------------ | ------------------------- |
| **Memory**      | “remember requirement matrix”              | Letta reflection / GEPA   |
| **Skill**       | new `requirements-audit/SKILL.md`          | Trace2Skill               |
| **Process**     | `plan → implement → verify`                | CGE / GEPA                |
| **Harness/Mod** | automatically inject requirement checklist | Letta Mods / Meta-Harness |

There's a natural progression:

```text
failure once
    ↓
episode note

failure repeatedly
    ↓
memory

reusable procedure
    ↓
skill

systematic workflow pattern
    ↓
process

cannot reliably solve via context
    ↓
harness/mod
```

This is particularly interesting because Letta Mods now explicitly support adapting context assembly, tools, commands and runtime behavior, and Letta describes the harness itself as a learnable form of memory. ([Letta][7])

So eventually a worker might discover:

```text
"I repeatedly forget to inspect the rubric."

Memory fix didn't solve it reliably.

Skill improved it somewhat.

Candidate Mod:
before entering implementation,
automatically inject requirements matrix
into active context.
```

Then MWGym evaluates the Mod.

That's **actual harness evolution**.

Meta-Harness gives strong evidence this is worth exploring: it evolves harness code from source, scores and prior traces, and reported improvements on classification, math and TerminalBench while sometimes reducing context consumption. ([arXiv][8])

---

# Trace2Skill fits almost perfectly

Don't create a Skill from one lucky trajectory.

Collect:

```text
83 software debugging runs
```

then cluster:

```text
successful
failed
cheap
expensive
regression-causing
fast
```

Trace2Skill's central idea is exactly this: analyze broad pools of trajectories in parallel, extract local lessons, then consolidate them into unified transferable skills rather than sequentially overfitting to individual runs. ([arXiv][9])

So:

```text
WorkerKit receipts
      +
Letta trajectories
      +
FailureVectors
      ↓
Trace2Skill
      ↓
candidate SKILL.md
      ↓
Git worktree
      ↓
MWGym/CGE evaluation
      ↓
merge/reject
```

Very natural.

---

# And CGE evolves the *other side*

Meanwhile the worker is being trained against evolving worlds:

```text
WorkerGenome evolution
          ↑
          │
   adversarial interaction
          │
          ↓
WorldGenome evolution
```

A worker gets better at stale-source research.

CGE notices.

It produces:

```text
stale source
+
duplicated secondary source
+
conflicting fresh low-authority source
```

Worker fails.

That produces a new learning signal.

So you have genuine co-evolution:

```text
                  ECONOMY
                    │
                 Oracle
                    │
             F1-F11 weights
                    │
                    ▼
             CGE WorldGenome
                    │
                adversary
                    │
                    ▼
              WorkerGenome
                    │
             Letta experience
                    │
                    ▼
             memory / skills
                    │
                    ▼
                stronger
                    │
                    └────→ CGE gets harder
```

And the world distribution remains anchored to real economic demand rather than arbitrary benchmark games.

---

# The custom thing worth building

I would therefore define Moltwork's core product technically as an:

## **Economic Evolution Meta-Harness**

Not another agent framework.

It provides five contracts:

```text
1. WorkerGenome
   What cognition is this?

2. WorldGenome
   What challenge is this?

3. ComputePolicy
   How should intelligence be purchased?

4. RunReceipt
   What actually happened?

5. PromotionDecision
   Did the mutation generalize?
```

Everything else can remain pluggable.

```text
Cognition:
  Letta
  Pydantic
  Claude Code
  Codex
  Hermes

World:
  CGE
  real Git repos
  Harbor occasionally

Evolution:
  GEPA
  Trace2Skill
  Letta reflection
  Letta Mods
  Meta-Harness-style search

Compute:
  BATS
  LiveLLM
  QDW
  provider APIs

Memory:
  Letta MemFS

Empirical organization:
  Hydra

Evidence:
  WorkerKit
```

That's much more defensible than making yet another general agent SDK.

---

# The full production loop I would freeze

```text
1 ORACLE
pick economically relevant opportunity/family

2 MWGYM
choose real task or CGE adversarial world

3 GIT
fresh repo/worktree
commit pristine state B0

4 FREEZE
WorkerVersion
WorldVersion
EvaluatorVersion
ComputePolicy
MarketSnapshot
TreasurySnapshot

5 HYDRA
retrieve a tiny LabBrief

6 LETTA
persistent agent
fresh STATEFUL conversation
cwd = work repo

7 PLAN
Letta interprets task + experience

8 ALLOCATE
TaskGraph enters Moltwork ComputeBroker

9 EXECUTE
free/cheap/direct/Pydantic workers
under BATS limits

10 SYNTHESIZE
Letta reviews and integrates results

11 GIT
commit final work B1

12 VERIFY
deterministic verifier / CGE

13 WORKERKIT
record artifact, costs, calls,
route decisions, hashes, outcome

14 HYDRA
project empirical result

15 REFLECT
trajectories + FailureVector

16 PROPOSE
memory / Skill / Process / Mod candidates

17 GIT WORKTREE
apply candidates away from production

18 MWGYM
incumbent vs candidate
on held-out adversarial worlds

19 CGE1
shrinkage + replace-if-wins

20 PROMOTE
merge candidate Git branch
or reject

21 REPEAT
Oracle weighting + harder CGE curriculum
```

That is the thing I would build.

## The immediate next implementation

Before adding anything else, fix `runtime-letta` so that **stateful is the default execution treatment**, `stateless` is a named control arm, and every run records:

```yaml
letta:
  agent_id:
  conversation_id:
  memory_commit_before:
  memory_commit_after:

workspace:
  base_sha:
  final_sha:

compute:
  model_requests:
  route_decisions:
  actual_cost:
```

Then implement exactly one custom Letta tool:

```text
moltwork_delegate(TaskSpec)
```

That tool is the doorway into:

```text
LiveLLM
→ Treasury
→ Hydra posterior
→ BATS
→ Direct/Pydantic/Letta-stateless executor
```

Once that works, you have the really compelling architecture:

> A persistent Letta worker can retain years of learned context, while Moltwork decides dynamically how much intelligence each piece of work deserves, trains the worker in economically relevant adversarial worlds, and only commits cognitive/harness mutations that win controlled Git-versioned experiments.

I agree with the underlying intuition: **Letta is too aligned with the direction of this project to replace**. Their 2026 work is moving directly into Git memory, memory evaluation, trajectory interchange, self-improving Mods, and persistent model-agnostic agents. The opportunity for Moltwork is to build the missing layer they are deliberately not building: **economic resource allocation + empirical capability measurement + adversarial curriculum + evolutionary promotion around those persistent agents.** ([Letta][10])

[1]: https://www.letta.com/blog/context-repositories/?utm_source=chatgpt.com "Introducing Context Repositories: Git-based Memory for Coding Agents | Letta"
[2]: https://www.letta.com/blog/introducing-the-letta-agent-sdk/?utm_source=chatgpt.com "Letta Agents SDK: An SDK for stateful agents | Letta"
[3]: https://www.letta.com/agent-sdk/?utm_source=chatgpt.com "Letta Agent SDK — the SDK for stateful agents"
[4]: https://pydantic.dev/docs/ai/guides/multi-agent-applications/?utm_source=chatgpt.com "Multi-agent Applications | Pydantic Docs"
[5]: https://arxiv.org/abs/2511.17006?utm_source=chatgpt.com "Budget-Aware Tool-Use Enables Effective Agent Scaling"
[6]: https://github.com/letta-ai/letta-agent-sdk/releases?utm_source=chatgpt.com "Releases · letta-ai/letta-agent-sdk · GitHub"
[7]: https://letta.one/blog/introducing-mods/?utm_source=chatgpt.com "Introducing Mods: Enabling Agents to Self-Improve through Harness-Level Adaptation | Letta"
[8]: https://arxiv.org/abs/2603.28052?utm_source=chatgpt.com "Meta-Harness: End-to-End Optimization of Model Harnesses"
[9]: https://arxiv.org/abs/2603.25158?utm_source=chatgpt.com "Trace2Skill: Distill Trajectory-Local Lessons into Transferable Agent Skills"
[10]: https://www.letta.com/blog/trajectory/?utm_source=chatgpt.com "Trajectory: A Standard Format for Agent Experience Data | Letta"
