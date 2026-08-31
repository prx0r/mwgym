# MWGym v2 — corrected architecture

## Key corrections from mwgym2

1. Reasoning events ≠ model calls (stream events from single response)
2. MiMo CAN disable thinking: `thinking.type: "disabled"` 
3. maxSteps:2 probably ignored (not in public SDK types)
4. stateless:true defeats learning purpose
5. MWGym learns WHEN to use Letta, not force it everywhere

## First experiment: fast-vs-Letta crossover

Same 100 simple tasks, 4 arms:
- A: direct model, one shot
- B: Letta stateless
- C: Letta stateful  
- D: dynamic router choosing A/C

Measure: success, model calls, tokens, latency, cost

## YGO keeps simulator local

Inner loop: fast policy (no LLM)
BATS decides when to invoke Letta/Hydra/strong model

## What to build first

1. ModelCall record (observability)
2. RuntimeProfile (genome settings)
3. Fast-vs-Letta crossover benchmark
4. Then YGO World 001
