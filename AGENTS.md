# MWGym

The gym where Moltwork workers train, compete, and evolve.

> **Part of Tom's Lab.** Read `/root/AGENTS.md` for credentials, box rules, and full context.

## What This Is

MWGym is the training and evolution layer. Oracle finds work, WorkerKit does it,
MWGym learns from how it went.

## Architecture (from Frozen Decisions)

```
                    ORACLE
          finds market opportunities
                     │
                         ▼
                    MOLTWORK
             campaign + scientist layer
                     │
      ┌──────────────┼──────────────┐
      │              │              │
      ▼              ▼              ▼
   LETTA          HARBOR          GEPA/
 persistent      WORLDS        OpenEvolve
 worker          evaluators    search/evolution
 cognition
      │              │              │
      └──────────────┼──────────────┘
                     ▼
                 WorkerRun
                     │
             WorkerKit evidence
                     │
               Trajectory
                     │
               evaluation
                     │
                     ▼
                 HYDRADB
           empirical experience graph
                     │
                     ▼
                 MOLTING
         ┌───────────┼───────────┐
         ▼           ▼           ▼
      Memory       Skill       Process
         │           │           │
         └───────────┼───────────┘
                     ▼
                 Git branch
                     │
               evaluate again
                     │
              promote / reject
```

## Pool Architecture (from Private Lab Spec)

A **Pool** is a shared capability/experience scope — a reusable body of
empirical experience, skills, doctrine, evaluators and priors that may
help with a task.

An opportunity can draw from **zero, one, or several pools** with
different relevance weights.

```
Pool = shared capability/experience scope
Venue = external earning/evaluation surface
Worker = persistent acting agent
Finding = evidence with tier system
```

### Finding Tiers

```
OBSERVATION → STUDIO_FINDING → TRANSFER_CLAIM → DOCTRINE
```

### Pool Examples

| Pool | Subdomains | Venues |
|------|------------|--------|
| forecasting | binary, numeric, multiple_choice | metaculus |
| compute.routing | model.selection, budget.allocation | local |
| software.implementation | api_endpoint, web_app, cli_tool | github, moltjobs |

## HydraDB — The Graph Database

**HydraDB is live.** Rust graph database on SlateDB, running in Docker.

```bash
# Status
docker ps | grep hydradb
# Ports: 7687 (Bolt), 8443 (HTTP), 9090 (Admin)

# Auth token
cat /root/workerkit/data/hydradb/auth-token
# → private-lab-hydradb-token-2026-secure
```

### Connection

```python
from neo4j import GraphDatabase

token = open('/root/workerkit/data/hydradb/auth-token').read().strip()
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', token))
```

### Cypher Syntax (limited — read this)

HydraDB implements a **deliberate subset** of OpenCypher. Key constraints:

| Feature | Support |
|---------|---------|
| `MATCH` | Yes, with id/label/property predicate required |
| `MERGE` | Yes, matched on id |
| `CREATE` | Relationship paths only (not nodes) |
| `RETURN` | `<binding>.<property>` or `count(*)` only |
| `DELETE` | Yes, after MATCH |
| `WHERE` | Boolean combos of property comparisons |
| Properties | integer, float, boolean, string literals only |

**Working patterns:**

```python
# Create node (use MERGE, not CREATE)
session.run('MERGE (n:Run {id: $id})', id='run-001')

# Create relationship
session.run('''
    MATCH (a:Run {id: $a_id}), (b:Run {id: $b_id})
    CREATE (a)-[:DEPENDS_ON]->(b)
''', a_id='run-001', b_id='run-002')

# Query with label
result = session.run('MATCH (n:Run) RETURN n.id AS id')
for r in result:
    print(r['id'])

# Count
result = session.run('MATCH (n:Run) RETURN count(*) AS count')
print(result.single()['count'])

# Delete
session.run('MATCH (n:Run) DETACH DELETE n')
```

**Broken patterns (DO NOT USE):**

```python
# ❌ RETURN n (must use n.property)
session.run('MATCH (n) RETURN n')

# ❌ RETURN count(n) (must use count(*))
session.run('MATCH (n) RETURN count(n) AS c')

# ❌ CREATE node (use MERGE)
session.run('CREATE (n:Run {id: "x"})')

# ❌ CREATE with RETURN
session.run('CREATE (n:Run) RETURN n')
```

### Restart

```bash
docker restart hydradb
# Or recreate:
docker run -d --name hydradb \
  -p 7687:7687 -p 8443:8443 -p 9090:9090 \
  -v /root/workerkit/data/hydradb/data:/data \
  -e GRAPH_ALLOW_PLAINTEXT=true \
  -e GRAPH_AUTH_TOKEN_FILE=/data/auth-token \
  ghcr.io/hydra-db/hydradb:latest
```

## What This Is

MWGym is the training and evolution layer. Oracle finds work, WorkerKit does it,
MWGym learns from how it went. This repo contains:

- **CGE worlds** — training environments (forecasting, software, research, compute routing)
- **Harnesses** — execution adapters (pydantic-bats, letta, forecasting)
- **Adversary** — mutates worlds based on failure vectors
- **Curriculum** — selects next worlds from MAP-Elites archive
- **LabBrief** — empirical memory generator for workers
- **Wired Loop** — the production loop: discover → train → execute → record → learn

## Architecture

```
ORACLE → opportunities
    ↓
WORKERKIT → execution + evidence
    ↓
MWGYM → measure + learn + evolve
    ↓
┌───────────┬───────────┬───────────┐
│ Forecast  │ Software  │ Live jobs │
│ World     │ World     │ Oracle    │
│ (CGE)     │ (CGE)     │ opport-   │
│           │           │ unities   │
└───────────┴───────────┴───────────┘
```

## Key Files

| File | What |
|------|------|
| `mwgym/wired_loop.py` | Production loop — the main entry point |
| `mwgym/schema/world.py` | WorldGenome, FailureVector, GateResult, CapabilityScore |
| `mwgym/worlds/schema.py` | FamilyWorldSpec + 11 registered task families |
| `mwgym/worlds/cge_adapter.py` | Compiles WorldGenome → executable CG worlds |
| `mwgym/worlds/adversary.py` | Failure-guided WorldGenome mutation, MAP-Elites |
| `mwgym/worlds/curriculum.py` | MAP-Elites curriculum selection |
| `mwgym/harnesses/pydantic_bats.py` | PydanticAI-style harness with BATS routing |
| `mwgym/harnesses/forecasting.py` | Metaculus forecasting harness |
| `mwgym/lab_brief.py` | Empirical memory generator |
| `mwgym/workspace.py` | Git lab + worktrees |
| `mwgym/metaculus.py` | Metaculus API client |
| `mwgym/forecasting_loop.py` | Metaculus learning loop |
| `mwgym/oracle_connector.py` | Fetch opportunities from Oracle |

## Run Commands

```bash
# Full wired loop
python3 mwgym/wired_loop.py --rounds 10 --family compute.routing --harness pydantic-bats

# Forecasting loop (once MetaculusVenue is wired)
python3 mwgym/forecasting_loop.py --batch-size 10

# Check lab state (TODO: Wire HydraDB client)
# python3 -c "from mwgym.hydra_unified import UnifiedHydra; ..."
```

## Current Priority: ForecastingWorld

The CGE adapter (`worlds/cge_adapter.py`) registers 3 forecasting families in schema
but has no `ForecastingWorld` class in `_WORLD_CLASSES`. Need to build one with:

- Hidden truth (resolution value)
- Observable state (question text, community prediction, close time)
- Actions: RESEARCH, SUBMIT_FORECAST, UPDATE
- Scoring: Brier/log score against resolution
- FailureVector → adversary for curriculum

## Progression

Level 0: YGO (closed deterministic world)
Level 1: Asset generation (sandboxed)
Level 2: Coding/search benchmarks
Level 3: Historical Moltwork jobs
Level 4: Real low-risk opportunities
Level 5: Fully live work
