# MWGym

The gym where Moltwork workers train, compete, and evolve.

## Architecture

```
ORACLE → opportunities
    ↓
WORKERKIT → execution + evidence
    ↓
MWGYM → measure + learn + evolve
    ↓
┌───────────┬───────────┬───────────┐
│ YGO       │ Roblox    │ Live jobs │
│ determin- │ asset     │ Oracle    │
│ istic     │ work      │ opport-   │
│ world     │ world     │ unities   │
└───────────┴───────────┴───────────┘
```

## Central Abstraction: DecisionPoint

Every worker run produces decision points:
- what to do
- what it cost
- what the alternatives were
- what actually happened

## Progression

Level 0: YGO (closed deterministic world)
Level 1: Asset generation (sandboxed)
Level 2: Coding/search benchmarks
Level 3: Historical Moltwork jobs
Level 4: Real low-risk opportunities
Level 5: Fully live work
