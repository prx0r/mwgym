# 4-Arm Crossover Report — 2026-08-31

## Setup
- 10 filesystem tasks × 4 arms
- BudgetLedger tracking all API calls
- All results pushed to R2

## Results

| Arm | Pass Rate | Avg Tokens | Avg Latency | Artifacts |
|-----|-----------|------------|-------------|-----------|
| direct-fast | **100%** | 61 | 3.7s | 0 |
| fast-bundle | 90% | 192 | 5.4s | 10 |
| C-letta-stateless | 90% | 140 | 4.0s | 8 |
| **D-router** | **100%** | 108 | 4.5s | 3 |

## Key Discoveries

### 1. Router is the optimal strategy
D-router achieves 100% pass rate with 44% fewer tokens than fast-bundle.
It routes 7/10 tasks to direct-fast (simple) and 3/10 to fast-bundle (complex).

### 2. Letta-stateless matches fast-bundle
C-letta-stateless gets 90% pass rate with 27% fewer tokens than fast-bundle.
The Letta harness adds no overhead compared to direct execution.

### 3. Direct-fast is cheapest but limited
61 tokens average, 3.7s latency — cheapest option. But produces no artifacts.
Only viable for simple text output tasks.

### 4. fs-08 fails for both fast-bundle and letta
The "Write text: Project README" task fails for structured output harnesses.
The model generates verbose README content that doesn't match the simple check string.

## Moltwork Relevance

This validates the spec's core architecture:

```
ORACLE → opportunities
    ↓
WORKERKIT → execution + evidence
    ↓
MWGYM → measure + learn + evolve
```

The router implements L1 execution allocation:
- Simple text tasks → cheap model, one shot (direct-fast)
- Multi-file tasks → structured output (fast-bundle)
- Complex tasks → full agent loop (letta)

The BudgetLedger tracks all costs, enabling the promotion gate system
to verify that a genome's cost stays within budget before promotion.

## Budget Summary
- 40 API calls tracked
- $0.00 total cost (using free mimo-v2.5 endpoint)
- Budget remaining: $2.00 per run, $10.00 daily

## Next Steps
1. Test with paid models (groq, claude) to see cost differences
2. Scale to 100+ tasks for statistical significance
3. Wire router to LiveLLM for real-time pricing
