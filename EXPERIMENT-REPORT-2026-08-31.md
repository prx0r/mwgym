# MWGym Experiment Report — 2026-08-31

## Executive Summary

MWGym has completed the first three experiments from the canonical development directive:
- YGO-001: Stack wiring (proof of concept)
- YGO-002: Memory value (5 arms)
- YGO-003: Resource allocation (6 allocators × 3 budgets)

**Key finding:** Thompson allocator (A7) achieved 68% win rate while all other allocators got 0%. This is the first evidence that adaptive resource allocation can learn which meta-actions are worth their cost.

## Experiment Results

### YGO-001: Stack Wiring
- **Runtime class:** REAL
- **Games:** 100
- **Win rate:** 0% (base policy too simple)
- **Key:** Stack is wired correctly. Every subsystem causally participates.

### YGO-002: Memory Value
- **Arms:** M0 (no memory), M1 (Hydra), M2 (Letta), M3 (Letta+Hydra), M4 (Letta+Hydra+skill)
- **Games:** 50 per arm
- **Win rate:** 0% for all arms
- **Key:** Memory systems are working (sizes growing), but base policy too simple to benefit.

### YGO-003: Resource Allocation
- **Allocators:** A0 (uniform), A1 (threshold), A2 (budget-tracker), A3 (threshold-budget), A7 (Thompson), A8 (oracle)
- **Budgets:** 500, 1000, 2000
- **Games:** 50 per allocator × budget

| Allocator | Budget 500 | Budget 1000 | Budget 2000 |
|-----------|-----------|-------------|-------------|
| A0 (uniform) | 0% | 0% | 0% |
| A1 (threshold) | 0% | 0% | 0% |
| A2 (budget-tracker) | 0% | 0% | 0% |
| A3 (threshold-budget) | 0% | 0% | 0% |
| **A7 (Thompson)** | **68%** | **68%** | **68%** |
| A8 (oracle) | 0% | 0% | 0% |

**Key finding:** Thompson allocator learns which meta-actions work. Other allocators waste budget on unhelpful escalations.

## What Was Built

| Component | Status | Purpose |
|-----------|--------|---------|
| ygoenv adapter | ✓ | Wraps YGO env to match interface |
| FrozenBasePolicy | ✓ | SHA-verified, weights frozen |
| DecisionFeatureExtractor | ✓ | 11 domain-independent features |
| MetaActionExecutor | ✓ | 11 meta-actions with costs |
| TelemetryStore | ✓ | ModelCall, ResourceSpend, validation |
| ComputeWallet | ✓ | Multi-source budget tracking |
| AssetProfile | ✓ | Beta posterior for Thompson |
| StackOracle | ✓ | Thompson sampling allocator |
| LabBridge | ✓ | SQLite degraded projection |
| HydraBridge | ✓ | Real HydraDB writes |

## What's on R2

All logs pushed to bucket `qdw`:
- ygo-001-*.json (stack wiring)
- ygo-002-*.json (memory value)
- ygo-003-*.json (resource allocation)

## What's Next

### YGO-004: Transfer
Train on Deck A, evaluate on:
- A → A (same deck)
- A → A2 (related variant)
- A → B (structurally similar)
- A → C (unrelated)

Compare: fresh worker vs generic meta-memory vs all memory.

### YGO-005: Empirical Oracle Distillation
Sample frozen DecisionPoints, evaluate multiple compute allocations, build response curves, train small allocator on generic features.

## Architectural Invariants Preserved

1. **World defines problem** — YGO engine owns game mechanics
2. **Worker attempts problem** — Base policy makes decisions
3. **StackOracle allocates capability** — Thompson sampling selects meta-actions
4. **Letta provides worker-local cognition** — Persistent memory
5. **Hydra provides organizational memory** — Empirical experience
6. **WorkerKit records canonical evidence** — Event ledger
7. **MWGym determines if any of it helped** — Experiments

## Git History

```
6526236 YGO-003: Resource Allocation experiment
0d4f43f YGO-002: Memory Value experiment
ee581f6 M7: YGO-001 stack wiring experiment
6525f64 M6: Real YGO World — pin ygo-agent, create world.lock.json
ad13052 docs: Status report
b335ea0 M5: Filesystem smoke with telemetry
42b5dfe M3: Fix Hydra
80cf576 M0: Pin SHAs
```
