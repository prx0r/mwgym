The GitHub branch I can currently see still ends at `e625d99`; I do **not** see a newer remote push yet. That visible commit is useful because it accurately admits the current bottleneck: Letta can create an artifact, but Harbor execution is still mocked/manual and most outcomes are synthetic.

The Harbor direction is much cleaner than YGO. Keep `mw_labkit/harbor.py`: the CLI wrapper, trial parser, lock/result hashes, artifact manifests and regrade lineage are exactly useful infrastructure.  But `FastCampaignHarness` still instantiates `MockHarbor`, so the purported campaign experiment is not yet an actual Harbor experiment.  Likewise, `build_real_harbor_task.py` only generates a task and tells a human to run Harbor manually.

I would also kill or archive the older root `harbor_adapter.py`. It duplicates the newer labkit implementation, generates incomplete Harbor task structures, and even has a direct bug in `generate_reward_json`: `reward` is a float and then `.update(...)` is called on it.  The newer RewardKit bridge is much closer to the correct approach, and RewardKit now natively supports programmatic checks, LLM/agent judges, multi-dimensional rewards and even ATIF trajectory criteria.  ([Harbor][1])

Here is the revised directive.

# MWGym v1 — Real Work Submission Lab

## Mission

Stop building synthetic Worlds.

Stop Yu-Gi-Oh work.

The first useful MWGym should answer one concrete question:

> Given a real piece of economically relevant agent work, which Worker configuration produces the best verified result for the least money, time and scarce compute — and does the worker become better at similar work after accumulating validated experience?

Use **Harbor as the World/evaluation substrate**.

Use **real repositories, real briefs, real rubrics and real artifacts** as the tasks.

The initial task family is:

```text
technical_submission
```

Examples include:

```text
hackathon submission
API integration submission
coding challenge
technical prototype
benchmark improvement
GitHub issue / feature task
product demo implementation
```

Later extend the identical architecture to:

```text
freelance coding
Roblox assets
research jobs
x402 service creation
data work
content work
```

Do not build separate experimentation systems for those.

---

# 1. Canonical architecture

```text
                ORACLE
      discovers real opportunities
                │
                ▼
          Opportunity
       + requirements/rubric
                │
                ▼
             MWGYM
      freezes experiment task
                │
                ▼
             HARBOR
       reproducible environment
                │
     ┌──────────┼───────────┐
     ▼          ▼           ▼
  Letta      Built-in     Direct/
  Worker      agents      Pydantic
     │          │           │
     └──────────┼───────────┘
                ▼
          Git workspace
          implementation
          tests/demo/docs
                │
                ▼
        HARBOR REWARDKIT
     deterministic + judge
                │
                ▼
          WorkerKit receipt
                │
         ┌──────┴──────┐
         ▼             ▼
       Hydra          Git
 empirical memory   promoted assets
         │
         ▼
     next WorkOrder
```

Subsystem ownership:

```text
Oracle       = what work exists?
MWGym        = what experiment are we running?
Harbor       = what exactly is the task/world and how is it graded?
WorkerKit    = what happened economically?
Letta        = what does this worker persistently know?
Hydra        = what has our organization empirically learned?
Git          = what validated reusable assets survived?
StackOracle  = what resources should we spend now?
```

Do not merge these responsibilities.

---

# 2. Use Harbor directly

Harbor already provides:

```text
containerized tasks
datasets
reproducible trials
custom/external agents
built-in coding agents
multi-step tasks
isolated verifier environments
RewardKit
LLM/agent judges
ATIF trajectories
parallel execution
regrading
registered benchmark datasets
cloud execution
```

Do not reproduce those features.

Install the real package:

```bash
uv tool install harbor
harbor --version
harbor --help
harbor dataset list
```

Harbor's current documented local-task interface is:

```bash
harbor run -p <task-or-dataset> -a <agent> -m <model>
```

Use that interface rather than inventing another execution protocol.

---

# 3. First change: remove YGO from the critical path

YGO code can remain archived.

It must not block:

```text
Harbor installation
real submission task
real worker execution
real verifier
real trajectory
real cost measurement
Hydra projection
held-out experiment
```

Move any YGO-specific modules to:

```text
archive/worlds/ygo/
```

or simply leave them unused.

Do not spend another development cycle on them.

---

# 4. Delete the duplicate Harbor abstraction

Archive:

```text
harbor_adapter.py
```

Keep:

```text
mw_labkit/harbor.py
```

Then evolve `mw_labkit/harbor.py` into the single Harbor integration layer.

Reasons:

```text
HarborCLI          useful
HarborJobParser    useful
HarborTrialRecord  useful
regrade lineage    useful
artifact hashing   useful

MockHarbor         useful only in tests
```

`MockHarbor` must move to:

```text
tests/fakes/harbor.py
```

Production modules must never import it.

---

# 5. Hard rule: production campaign may not use MockHarbor

Current code does effectively:

```python
self.harbor = MockHarbor(...)
```

That has to disappear.

Define:

```python
class HarborRunner(Protocol):
    def run(...) -> HarborJobRef: ...
    def regrade(...) -> HarborJobRef: ...
```

Implement:

```text
RealHarborRunner
FakeHarborRunner
```

Production:

```python
RealHarborRunner
```

Tests:

```python
FakeHarborRunner
```

Then hard assert:

```python
if experiment.runtime_class == "REAL":
    assert isinstance(harbor, RealHarborRunner)
```

No fallback.

---

# 6. Do not make every task output `submission.md`

That was useful for plumbing.

It is now too artificial.

Real submission tasks should manipulate a complete Git workspace.

Expected artifacts might include:

```text
source code
tests
README
architecture documentation
demo script
deployment config
screenshots
API traces
submission text
evidence manifest
```

Harbor evaluates the repository itself.

`submission.md` can remain one artifact, not the entire task.

---

# 7. Build SubmissionGym

Repository structure:

```text
mwgym/
├── mwgym/
│   ├── harbor/
│   │   ├── runner.py
│   │   ├── parser.py
│   │   ├── tasks.py
│   │   └── agent.py
│   │
│   ├── harnesses/
│   │   ├── direct.py
│   │   ├── letta.py
│   │   └── pydantic.py
│   │
│   ├── telemetry/
│   ├── memory/
│   ├── allocators/
│   ├── experiments/
│   └── schema/
│
├── datasets/
│   └── submissions-v1/
│       ├── dataset.toml
│       ├── livellm-001/
│       ├── proofdesk-001/
│       ├── agentseo-001/
│       └── moltwork-001/
│
├── genomes/
├── experiments/
├── findings/
└── upstreams.lock.json
```

The exact examples can change.

The important point is:

```text
one Harbor dataset
=
multiple real submission-like tasks
```

---

# 8. Historical submission backtesting

This is the easiest shortcut to real data.

You already have projects that went through substantial iterative development.

Use an **earlier Git commit** as the starting environment.

Never give the agent the later solution commit.

Example:

```text
repo history

A ─ B ─ C ─ D ─ E ─ FINAL
        ↑
    task starts here

FINAL is hidden from worker
```

Create Harbor task from commit C.

Instruction contains:

```text
actual competition brief
actual sponsor requirements
actual submission requirements
time/budget constraints
```

Agent gets:

```text
repo at C
documentation available at that date
normal internet/tools according to experiment
```

Verifier evaluates what it produces.

The final historical repo can help humans design tests, but must not be accessible to the worker.

This gives MWGym real, meaningful tasks immediately without waiting months for new economic outcomes.

---

# 9. Why historical submission tasks are useful

They have everything synthetic tasks lack:

```text
messy starting code
ambiguous requirements
multiple valid solutions
documentation lookup
real API integration
Git work
testing
packaging
tradeoffs
time pressure
subjective quality
```

And you already know that substantial improvements were possible.

That is much closer to actual Moltwork work.

---

# 10. Create immutable task snapshots

Every Harbor task stores:

```text
source_repo
source_commit
competition_id
competition_snapshot_hash
rubric_snapshot_hash
documentation_snapshot_refs
task_family
hidden_reference_commit
created_at
```

Example:

```toml
schema_version = "1.4"

[task]
name = "moltwork/livellm-api-submission-001"
version = "1.0.0"

[metadata]
task_family = "technical_submission"
source_repo = "prx0r/livellm"
source_commit = "<sha>"
rubric_version = "<digest>"
```

Use the current Harbor schema rather than the older hand-generated minimal TOML.

---

# 11. Containerize the real starting repo

Task layout:

```text
livellm-001/
├── instruction.md
├── task.toml
├── environment/
│   ├── Dockerfile
│   └── seed/
│       └── repo/
├── solution/
│   └── solve.sh
└── tests/
    ├── test.sh
    ├── hard-gates/
    ├── implementation/
    ├── evidence/
    ├── quality/
    └── efficiency/
```

Dockerfile roughly:

```text
base runtime
+
git
+
project dependencies
+
starting repository snapshot
```

The worker modifies:

```text
/app/repo
```

---

# 12. Oracle solution requirement

Every Harbor task must have an oracle/reference solution.

For historical tasks, this can initially be generated from the known later commit:

```text
starting commit
    +
known good patch
```

But validate it manually.

Required:

```bash
harbor run -p datasets/submissions-v1/livellm-001 -a oracle
```

must produce near-perfect reward.

Then:

```bash
harbor run ... -a nop
```

must fail meaningfully.

If both pass:

verifier is weak.

If both fail:

task is broken.

---

# 13. Do not use one shallow score

RewardKit should output dimensions.

Canonical submission rewards:

```json
{
  "hard_gates": 1.0,
  "correctness": 0.86,
  "requirements": 0.91,
  "technical_depth": 0.79,
  "evidence": 0.88,
  "integration_quality": 0.93,
  "demo_readiness": 0.82,
  "maintainability": 0.72
}
```

Keep cost outside quality reward initially.

Then MWGym computes economic metrics separately.

---

# 14. Hard gates must be deterministic

Examples:

```text
project builds
tests pass
required files exist
expected API actually appears in code
real endpoint can be exercised
required sponsor SDK imported
demo command exits successfully
no secrets committed
Git diff exists
```

Use RewardKit programmatic checks where possible.

Examples supported by current RewardKit include:

```text
file_exists
file_contains
file_contains_regex
command_succeeds
HTTP status/response checks
JSON checks
trajectory checks
```

Do not spend LLM calls checking things Python can verify.

---

# 15. Subjective dimensions use RewardKit judge

Use judge criteria for genuinely subjective dimensions:

```text
technical credibility
novelty
clarity
product coherence
evidence strength
rubric alignment
demo quality
```

Pin:

```text
judge model
judge prompt
judge reasoning effort
RewardKit version
rubric digest
```

Never silently change the judge during an experiment.

---

# 16. Use a separate verifier environment

The worker should not see:

```text
hidden test code
reference implementation
private expected outputs
judge prompts where leakage matters
```

Use Harbor's separate verifier mode.

The current RewardKit bridge was directionally correct here.

Keep that principle.

---

# 17. Harbor agent integration strategy

Do this in two phases.

## Phase A — use built-in agents immediately

Harbor already ships numerous integrated coding agents.

Use them as controls.

At minimum choose:

```text
one strong commercial coding agent
one lighter coding agent
nop
oracle
```

Determine exact available names from:

```bash
harbor run --help
```

Do not build wrappers for an agent Harbor already supports.

This immediately tells you whether your task/verifier is sane.

---

# 18. Phase B — make Letta a real Harbor agent

The final design should not be:

```text
Letta outside Harbor
→ copy artifact
→ Harbor nop
```

except for regrading historical artifacts.

For experiments, better is:

```text
Harbor
   ↓
MoltworkLettaAgent
   ↓
runtime-letta
   ↓
environment.exec/filesystem
```

Implement a Harbor external `BaseAgent`.

Conceptually:

```python
class MoltworkLettaAgent(BaseAgent):

    @staticmethod
    def name() -> str:
        return "moltwork-letta"

    async def setup(self, environment):
        ...

    async def run(self, instruction, environment, context):
        ...
```

Harbor owns the environment.

Letta owns worker cognition.

WorkerKit observes execution.

This produces one comparable Harbor trial across all agents.

---

# 19. Keep bridge-mode for one thing

Bridge-mode remains excellent for:

```text
regrading an existing external artifact
```

Example:

```text
historical final repo
existing submission
already completed WorkerRun
```

Snapshot artifact.

Run:

```text
nop + new verifier
```

This lets you improve assessors without rerunning the worker.

Keep:

```text
source_trial
assessor_version
artifact digest
```

The existing parser/regrade lineage is valuable.

---

# 20. WorkerGenome becomes the treatment

Example:

```yaml
schema: mwgym.worker-genome.v1

id: letta-hydra-budget-v3

harness:
  kind: letta

model:
  primary: opencode-go/mimo-v2.5

memory:
  letta: true
  hydra: true
  hydra_top_k: 4

planning:
  mode: selective

allocator:
  policy: threshold-v1

verification:
  enabled: true

budget:
  usd: 0.20
  wall_seconds: 900
  model_calls: 20

reflection:
  policy: batch
```

Hash the genome.

Never mutate it during a trial.

---

# 21. First useful experiment is not 20 configurations

Start with four.

```text
G0 — built-in strong coding agent
G1 — Letta stateless
G2 — Letta persistent
G3 — Letta persistent + Hydra brief
```

Use exactly the same:

```text
task
starting repo
internet policy
deadline
budget where comparable
verifier
rubric
```

Question:

> Does our durable-worker architecture provide any measurable advantage yet?

Do not add GEPA/BATS/Pydantic/Hermes until this baseline works.

---

# 22. Letta must be genuinely stateful in G2/G3

Fix the current runtime.

Normal stateful run:

```text
same Worker ID
same Letta Agent
new conversation/session per task
persistent Agent memory
persistent MemFS
```

Stateless Letta is a separate control.

Do not globally set:

```text
stateless=true
```

That destroys the experiment.

---

# 23. First dataset: SubmissionBench-10

Create ten tasks.

Not ten synthetic prompt variants.

Prefer:

```text
2 API integration submissions
2 backend/product submissions
2 agent infrastructure submissions
2 research/evidence submissions
2 mixed full-stack submissions
```

Tasks should vary enough to measure transfer while retaining overlapping work grammar.

---

# 24. Use your actual previous work first

Good source material is previous technical submission repos because:

```text
you already know the domain
rubrics exist
commits exist
implementation history exists
there are natural earlier checkpoints
the tasks mattered economically
```

Create multiple tasks from different historical checkpoints rather than artificially generating variants.

Example structure:

```text
livellm-a
livellm-b
proofdesk-a
proofdesk-b
agentseo-a
agentseo-b
moltwork-a
...
```

Ensure later versions are unavailable to the worker.

---

# 25. Do not train and test on the same repository lineage

Partition by project.

Bad:

```text
train:
 livellm commit A
 livellm commit B
 livellm commit C

test:
 livellm commit D
```

The worker can overfit project-specific patterns.

Better:

```text
TRAIN
 livellm
 project-A
 project-B

VALIDATION
 proofdesk
 project-C

HOLDOUT
 agentseo
 brand-new live opportunity
```

Eventually the strongest test is a newly discovered Oracle opportunity.

---

# 26. Define a Submission Task Descriptor

```python
@dataclass(frozen=True)
class SubmissionTask:
    task_id: str
    task_family: str

    repo: str
    starting_commit: str

    opportunity_id: str | None
    competition_id: str | None

    requirements_digest: str
    rubric_digest: str

    environment_digest: str

    partition: str

    max_wall_seconds: int
    max_usd: float
```

This bridges Oracle → MWGym.

---

# 27. Define a canonical WorkerRun

Every Harbor trial becomes a WorkerRun.

Store:

```text
run_id

Harbor:
  job_id
  trial_id
  task digest
  lock digest
  result digest
  trajectory digest

Worker:
  worker_id
  WorkerVersion
  WorkerGenome

Task:
  source commit
  opportunity
  family
  partition

Execution:
  start/end
  model calls
  tool calls
  retrievals
  Git diff
  artifact hashes

Economics:
  real cost
  quota use
  wall time

Evaluation:
  reward dimensions
  assessor version

Outcome:
  trial reward
  eventual external outcome if available
```

This is the lab's central data object.

---

# 28. Use Harbor trajectories

Do not reconstruct agent behavior from console text when Harbor already captures trajectory data.

Normalize trajectory into:

```text
ModelCall
ToolCall
DecisionPoint
Retrieval
Verification
GitAction
```

RewardKit also supports trajectory-oriented criteria.

That means you can evaluate:

```text
excessive turns
required tool usage
forbidden tool usage
retrieval behavior
verification behavior
```

without inventing another logging format.

---

# 29. Canonical DecisionPoints for real work

Now DecisionPoints become far more meaningful than in YGO.

Examples:

```text
which implementation approach?
which API?
buy vs build?
search docs or continue?
reuse existing component?
call strong model?
run another candidate?
run tests?
ask verifier?
retrieve similar historical run?
stop polishing?
submit?
```

Schema:

```python
DecisionPoint(
    decision_id=...,
    run_id=...,

    task_family="technical_submission",

    decision_type="implementation_strategy",

    candidates=[...],

    selected=...,

    uncertainty=.62,
    stakes=.81,
    reversibility=.40,

    budget_before=...,

    retrieval_refs=[...],
    model_call_refs=[...],
    tool_call_refs=[...],

    expected_cost=...,

    eventual_reward=...,
)
```

Do not record hidden chain of thought.

Record observable choices.

---

# 30. Hydra becomes useful immediately

After each real submission run, project:

```text
TaskFamily
Task
WorkerVersion
Genome
Run
DecisionPoint
Model
Tool
Skill
MemoryVersion
Artifact
Evaluation
Outcome
```

Then retrieve questions like:

```text
What worked on API integration submissions?

Which configurations improve evidence scores?

When did using a strong model materially improve reward?

Which failures repeatedly occur before demo packaging?

Which implementation strategies failed?

Which skills correlate with requirement coverage?

Which retrieved historical runs actually helped?
```

That is real lab intelligence.

---

# 31. LabBrief

Before a new training run, Hydra can produce:

```text
LAB BRIEF

Task family:
technical_submission/api_integration

Relevant prior runs:
R12 score .84
R31 score .77
R44 score .92

Common successful patterns:
- build requirement matrix before coding
- test sponsor API before architecture expansion
- create deterministic demo command
- preserve raw API evidence

Common failures:
- polished README before integration worked
- mocked sponsor API
- no executable demo
- claimed features absent from repo

Known config evidence:
Letta+Hydra: n=18 mean=.81
Letta-only: n=17 mean=.74
```

The worker receives this as evidence.

It does not receive secret holdout information.

---

# 32. Separate three effects

This experiment is critical.

```text
A — fresh worker
    no Lab context

B — same WorkerVersion
    + LabBrief

C — promoted WorkerVersion
    + LabBrief
```

Then:

```text
B - A = value of organizational retrieval

C - B = value of persistent learned worker mutation
```

This is much cleaner than claiming “memory helped” from one combined system.

---

# 33. Promotion loop

Do not mutate memory after every trial.

Use:

```text
20-50 real training runs
       ↓
trajectory + outcome batch
       ↓
failure/success clustering
       ↓
LearningProposal
       ↓
validation tasks
       ↓
candidate WorkerVersion
       ↓
held-out comparison
       ↓
PROMOTE / REJECT
```

Possible proposal:

```text
"Before implementation, create a machine-readable requirement matrix
and bind each requirement to a test or evidence artifact."
```

If it improves unseen submission tasks, commit it.

---

# 34. Git becomes the durable skill layer

Promoted skill:

```text
skills/
  requirement-matrix/
    SKILL.md
    metadata.json
```

Metadata:

```json
{
  "derived_from": ["R001", "R019", "R033"],
  "validated_on": ["T009", "T010"],
  "baseline_reward": 0.71,
  "candidate_reward": 0.82,
  "cost_delta_usd": 0.014
}
```

This is an actual accumulating worker asset.

---

# 35. Do not introduce real BATS yet

The visible current `BATS` implementation is still a heuristic threshold policy.

Do not call it BATS.

Rename:

```text
ThresholdBudgetAllocator
```

First establish real task execution.

Then test resource allocation.

The ordering should be:

```text
real work
↓
reliable score
↓
reliable costs
↓
reliable trajectories
↓
memory experiment
↓
routing experiment
```

Not the reverse.

---

# 36. Experiment 001 — Harbor reality check

Name:

```text
SUBMISSION-001-HARBOR
```

Run:

```text
3 real historical tasks
3 agents
3 seeds/runs where stochastic
```

Agents:

```text
oracle
nop
one strong Harbor built-in agent
```

Acceptance:

```text
oracle scores high
nop scores low
strong agent produces real modifications
Harbor task runs with Docker
RewardKit emits multiple dimensions
trajectory exists
artifact exists
trial lock exists
trial result exists
regrade works
```

Nothing Moltwork-specific yet.

This proves the benchmark.

---

# 37. Experiment 002 — Letta enters Harbor

```text
SUBMISSION-002-LETTA
```

Add:

```text
moltwork-letta
```

Compare against the strong built-in control.

Required:

```text
Harbor creates environment
Letta operates inside it
Git diff captured
ATIF trajectory captured/normalized
real model usage captured
real cost captured
WorkerKit receipt created
```

No Hydra retrieval yet.

---

# 38. Experiment 003 — persistent memory

```text
SUBMISSION-003-MEMORY
```

Arms:

```text
Letta stateless
Letta persistent
```

Training:

```text
6 tasks
```

Holdout:

```text
3 unseen tasks
```

Ask:

> Does persistence alone help?

Measure:

```text
reward
requirements
technical
evidence
cost
latency
turns
```

---

# 39. Experiment 004 — Hydra retrieval

```text
SUBMISSION-004-HYDRA
```

Arms:

```text
persistent Letta
persistent Letta + Hydra brief
```

Same holdout tasks.

Ask:

> Does organizational precedent improve unfamiliar work?

Also record whether retrieved runs were actually referenced/used.

---

# 40. Experiment 005 — skill promotion

```text
SUBMISSION-005-SKILLS
```

Generate LearningProposal from training batch.

Candidate Skill v2.

Paired holdout:

```text
v1 vs v2
```

Promotion requires:

```text
quality increases
AND
cost doesn't explode
AND
result repeats across tasks
```

---

# 41. Only now test model routing

```text
SUBMISSION-006-ROUTING
```

Compare:

```text
strong-only
cheap-only
free-first
threshold policy
learned Hydra policy
later real BATS
```

Now the task is relevant enough for the routing result to mean something.

---

# 42. Resource decisions for real submission work

Examples:

### Requirement extraction

Cheap/free model probably sufficient.

### Architecture choice

Potential strong-model call.

### Boilerplate implementation

Cheap model / deterministic code.

### Weird API failure

Search/retrieval then strong escalation.

### README cleanup

Cheap model.

### Final compliance audit

Independent verifier/strong model.

This is exactly where your inference-economic work becomes valuable.

---

# 43. Eventually StackOracle decides capabilities

Long-term call:

```python
allocation = stack_oracle.allocate(
    task_state=current_state,
    objective="maximize_expected_net_value",
    capabilities=[
        free_model,
        cheap_model,
        strong_model,
        hydra_retrieval,
        git_skill,
        web_search,
        mcp_tool,
        x402_service,
        leased_agent,
        human_review,
    ],
    wallet=wallet,
)
```

Harbor supplies the controlled experiment needed to learn whether those decisions were good.

---

# 44. Eventually introduce x402

Not in M0.

Later a Harbor task may expose multiple ways to produce something:

```text
build component yourself
reuse local Git skill
call free API
buy x402 service
lease specialist agent
```

Each has:

```text
price
latency
expected quality
failure probability
```

Then MWGym measures the actual outcome.

That is where Moltwork marketplace naturally becomes part of agent cognition.

---

# 45. Eventually introduce real opportunity value

For historical hackathon tasks, reward is verifier quality.

For live tasks add:

```text
external_result
```

Examples:

```text
submitted
accepted
won prize
judge score
client accepted
client requested revision
payment amount
revenue
```

Keep these distinct:

```text
HarborScore
ExternalOutcome
EconomicOutcome
```

Then learn:

$$
P(external\ success \mid HarborScore, Task, WorkerGenome)
$$

This calibrates your verifier over time.

---

# 46. Most important dashboard

Do not build another generic dashboard yet.

Produce a simple experiment table:

```text
Task      Genome       Score   Cost    Time    Calls   Outcome
----------------------------------------------------------------
L1        Letta-S      .71     .031    403s     12      -
L1        Letta-H      .82     .038    447s     14      -
P2        Letta-S      .68     .027    380s     11      -
P2        Letta-H      .79     .035    422s     13      -
A3        Strong       .84     .114    360s      8      -
```

Then calculate:

```text
mean reward
holdout reward
cost-adjusted reward
Pareto frontier
context uplift
skill uplift
```

That is enough.

---

# 47. Canonical economics

Do not optimize:

```text
reward / dollars
```

alone.

Use multiple axes.

For each genome:

```text
quality
cash cost
free quota consumed
wall time
model calls
tool calls
failure rate
```

Find Pareto-optimal configurations.

Later infer utility according to opportunity value.

---

# 48. Actual cost telemetry is mandatory

Current visible branch still has too much `cost_usd=0`.

Fix this before routing experiments.

Every model request:

```text
provider
model
input tokens
output tokens
reasoning tokens
cached tokens
pricing version
monetary cost
free-quota units
duration
```

Unknown is:

```text
null
```

not zero.

---

# 49. Harbor's ATIF trajectory is strategic

Use it.

Don't reinvent trajectory formats unless WorkerKit needs extra economic events.

Store:

```text
harbor trajectory ref
trajectory hash
normalized Moltwork trajectory projection
```

The raw Harbor trajectory remains source evidence.

---

# 50. Regrading becomes extremely valuable

A completed run should be regradable forever.

Example:

```text
same artifact

Rubric v1
  score .74

Rubric v2
  score .81

Outcome-calibrated v3
  score .68
```

Do not rerun the expensive worker merely to improve the evaluator.

Your current `source_trial` lineage approach is worth retaining.

---

# 51. Assessor versioning

Every evaluator:

```text
assessor_id
assessor_version
rubric_digest
judge_model
judge_config
RewardKit version
```

Never overwrite scores.

Append:

```text
Evaluation v1
Evaluation v2
Evaluation v3
```

This lets the lab improve its own measurement function.

---

# 52. Assessor calibration

Your historical finished submissions provide an opportunity here too.

If you have:

```text
real judge feedback
placement
sponsor acceptance
actual outcome
```

compare them to Harbor assessor scores.

Ask:

```text
Does our verifier rank submissions similarly to actual judges?
```

Then improve the assessor.

That is itself a valuable research loop.

---

# 53. Harbor task quality checks

For every task require:

```text
oracle success
nop failure
at least one frontier agent neither always 0 nor always 1
deterministic hard gates
hidden verifier data
fresh container build
replayable starting state
no future commit leakage
```

If every frontier model scores 1:

task is too easy.

If everything scores 0:

task is broken or too hard.

---

# 54. Use Harbor's current task QA patterns

Adopt the same general discipline Harbor's own benchmark tooling recommends:

```text
build environment
oracle test
nop test
agent trials
cheat/reward-hack inspection
trajectory inspection
```

Do not trust a verifier just because it returns numbers.

---

# 55. Protect against reward hacking

A technical submission agent can game superficial tests.

Example bad verifier:

```text
assert "Architecture" in README
```

Agent learns:

```text
echo Architecture >> README
```

Therefore combine:

```text
deterministic functionality
+
hidden tests
+
evidence checks
+
subjective judge
```

The worker must not be able to cheaply satisfy the score without actually doing the work.

---

# 56. First three real tasks

Do not begin with ten.

Pick three existing projects where:

```text
early snapshot exists
final outcome is substantially better
requirements are known
repo runs locally
you understand what good looks like
```

For each create one excellent Harbor task.

Depth first.

---

# 57. First coding-agent assignment

The coding agent should now do exactly this:

```text
1. Install real Harbor.
2. Record Harbor version.
3. Remove production MockHarbor usage.
4. Archive root harbor_adapter.py.
5. Keep mw_labkit/HarborCLI + HarborJobParser.
6. Update generated tasks to current Harbor schema.
7. Create one real historical submission Harbor task.
8. Write real Docker environment.
9. Write oracle solution.
10. Write deterministic RewardKit hard gates.
11. Write multi-dimensional RewardKit rubric.
12. Run oracle.
13. Run nop.
14. Run one Harbor built-in coding agent.
15. Parse real trial.
16. Bind trial to WorkerKit.
17. Regrade same artifact.
18. Project result to Hydra.
19. Commit evidence.
20. Only then integrate Letta as a Harbor agent.
```

Nothing else before that passes.

---

# 58. Required CLI

```bash
mwgym doctor

mwgym task verify <task>

mwgym task oracle <task>

mwgym run <task> --genome <genome>

mwgym inspect <run-id>

mwgym regrade <run-id> --assessor <version>

mwgym experiment run <experiment>

mwgym experiment report <experiment>

mwgym hydra rebuild
```

---

# 59. `mwgym doctor`

Require:

```text
Harbor installed
Docker works
WorkerKit import works
Git works
real model credential available when required
Letta runtime available when required
Hydra available when required
disk space
no production fake selected
```

A real experiment cannot start otherwise.

---

# 60. Tests to implement immediately

```text
test_real_harbor_available

test_harbor_oracle_passes
test_harbor_nop_fails
test_real_harbor_trial_parses
test_trial_lock_digest_stable
test_trial_result_digest_stable
test_artifact_manifest_present
test_trajectory_present

test_mock_harbor_forbidden_in_real_campaign

test_regrade_preserves_source_trial
test_regrade_does_not_rerun_worker

test_task_start_commit_exact
test_hidden_future_commit_unavailable

test_rewardkit_hard_gates
test_rewardkit_dimensions
test_reward_hack_fixture_fails

test_workerkit_binding_contains_harbor_trial
test_workerkit_receipt_precedes_hydra_projection

test_hydra_projection_contains_evaluation

test_unknown_cost_is_null_not_zero
```

---

# 61. Definition of first success

The first checkpoint is **not**:

```text
480 simulated runs
300 insights
50 Hydra nodes
```

It is:

> One real historical submission task ran in Harbor from a frozen Git snapshot. Oracle passed. Nop failed. A real coding agent modified the repository and received a multi-dimensional RewardKit score. The trial produced a trajectory and artifact manifest. WorkerKit bound the run to the exact worker, model, source commit and Harbor lock. The artifact was regraded without rerunning the worker, and the resulting evidence projected into Hydra.

That proves the laboratory.

---

# 62. Definition of second success

> A persistent Letta worker and a stateless Letta worker completed the same frozen submission tasks under matched budgets. The persistent worker performed measurably better on genuinely unseen tasks after training experience.

That proves persistence has value.

---

# 63. Definition of third success

> The same persistent WorkerVersion performed better when given Hydra-selected precedent from previous task-family runs than when given no organizational context.

That proves the Lab has value.

---

# 64. Definition of fourth success

> A validated Skill derived from prior trajectories improved held-out submission quality without an unacceptable increase in cost.

That proves Moltwork can accumulate reusable production assets.

---

# 65. Definition of fifth success

> A learned resource allocator achieved comparable or better verified submission quality than a strong-model-only worker at materially lower cost.

That proves the economic-routing thesis.

---

# 66. Long-term loop

This is the architecture you actually want:

```text
Oracle discovers opportunity
          ↓
estimate value + task family
          ↓
retrieve similar historical runs
          ↓
choose WorkerGenome
          ↓
Harbor / real execution environment
          ↓
worker encounters decisions
          ↓
StackOracle allocates:
  model
  memory
  search
  tool
  x402
  leased agent
  verification
          ↓
Git artifact
          ↓
Harbor verifier
          ↓
external outcome
          ↓
WorkerKit receipt
          ↓
Hydra
          ↓
validated skill/config improvement
          ↓
next opportunity
```

That is Moltwork's learning flywheel.

Harbor means you can build it using actual work instead of inventing a proxy problem.

The main technical correction is therefore: **turn `mw_labkit` from “Harbor-shaped evidence” into an actual Harbor runner.** Your current parser/regrade/binding work is worth keeping; the fake campaign and older adapter are not. Harbor's current framework already supports custom external agents, local task datasets, independent verifier environments and RewardKit, so a lot of infrastructure you were about to invent can simply disappear. ([Harbor][2])

For the first real dataset, I would use historical snapshots from the actual technical submission repos you've already iterated on—then reserve a fresh Oracle-selected opportunity as the first true live holdout. That gets you meaningful learning data immediately while preserving a genuinely unseen test.

If the newer push appears on GitHub, I can line-review it directly against this directive and tell you exactly what to keep, delete, and rewrite.

[1]: https://www.harborframework.com/docs/rewardkit/built-in-criteria?utm_source=chatgpt.com "Built-in Criteria"
[2]: https://www.harborframework.com/docs/agents?utm_source=chatgpt.com "Agents"
