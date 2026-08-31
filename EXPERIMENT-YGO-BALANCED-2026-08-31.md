# YGO Balanced Experiment Report — 2026-08-31

## Setup
- 120 games: 3 genomes × 4 opponents × 10 games each
- Equal action budgets (3 actions per turn per side)
- Fixed 5-card hands, 30 credits each

## Results

| Genome | vs passive | vs aggressive | vs defensive | vs economic |
|--------|-----------|---------------|--------------|-------------|
| wg-static | 100% | **40%** | 100% | 100% |
| wg-memory | 100% | **20%** | 100% | 100% |
| wg-memory-bats | 100% | **20%** | 100% | 100% |

## Key Discoveries

### 1. Aggressive opponent is the only real test
Passive, defensive, and economic opponents are too easy — all genomes win 100%.
Only the aggressive opponent (buys Power Boost, plays highest attack, always attacks)
creates meaningful variance. This means **opponent selection matters for benchmark validity**.

### 2. Static genome is most robust
wg-static gets 40% against aggressive, while memory/memory_bats get only 20%.
The static genome's simplicity (no exploration, no memory) makes it harder to beat
because it doesn't waste actions on unnecessary exploration.

### 3. Memory hurts against aggressive opponents
The memory and memory_bats genomes have higher exploration rates (0.1 and 0.15).
Against an aggressive opponent that maximizes damage, exploration is punished —
you spend an action on something suboptimal while the opponent hits you for 2800.

### 4. This validates the spec's core claim
The spec says MWGym should learn "when to use Letta, when to think, when to reuse."
This experiment shows that **exploration is not always good** — it depends on the opponent.
A smart worker should:
- Explore in passive environments (learn new strategies)
- Exploit in aggressive environments (maximize damage now)

This is exactly the explore/exploit tradeoff that BATS/CLEAR manages.

## Moltwork Relevance

In real Moltwork jobs:
- **Passive opponent** = simple task, no competition → safe to explore
- **Aggressive opponent** = high-stakes job, tight deadline → must exploit known strategies
- **Defensive opponent** = complex task, quality matters → careful execution
- **Economic opponent** = budget-constrained job → optimize cost

The genome that wins depends on the environment. MWGym's job is to map
(environment type) → (optimal genome configuration).

## Next Steps
1. Run 500+ games with aggressive opponent to get stable win rates
2. Test genome mutations (vary exploration_rate against aggressive)
3. Wire BudgetLedger to track cost per decision
