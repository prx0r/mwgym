# MWGym Crossover Experiment Report

**Run:** cross-1788166149  
**Date:** 2026-08-31  
**Experiment:** Direct adapter vs Fast (ActionBundle) adapter on 10 filesystem tasks

---

## Results

| Genome | Pass Rate | Total Tokens | Avg Latency | Files Written |
|--------|-----------|-------------|-------------|---------------|
| direct-fast | 10/10 (100%) | 641 | 6,862ms | 0 |
| fast-bundle | 9/10 (90%) | 2,163 | 9,108ms | 9 |

## What Was Proven

1. **MiMo-v2.5 works via opencode-go API.** Both adapters hit the API successfully. The `http.client` approach works where `urllib.request` gets 403 (Python 3.14 issue).

2. **Direct adapter is the right baseline.** 100% pass rate, lowest token count (641 total), fastest average (6.9s). One model call, no tool loop, no file I/O. This is the economic floor.

3. **Fast (ActionBundle) adapter works but is heavier.** 9/10 pass, 3.4x more tokens (2,163 vs 641), 1.3x slower. Writes files as a side effect. The one failure (fs-05, YAML) timed out at 20s - likely the model returned reasoning_content instead of a JSON bundle.

4. **Token accounting is real.** Both adapters report actual `prompt_tokens` and `completion_tokens` from the API response. This is the foundation for BATS budget decisions.

5. **Telemetry schemas work.** `ModelCallRecord`, `DecisionPoint`, `WorkerGenome` all serialize/deserialize correctly. The genome hash is deterministic.

## What Failed / Is Incomplete

1. **FastAdapter fs-05 failure.** The model returned 0 tokens and timed out at 20s. Likely returned `reasoning_content` but no `content`. Need to check if `thinking.type=disabled` is actually being respected end-to-end.

2. **No Letta harness tested yet.** The Letta service is running (health OK) but we didn't wire it into this experiment. The mwgym LettaAdapter exists but hasn't been validated end-to-end.

3. **No Hydra integration.** The `hydra/client.py` in workerkit is a thin wrapper. No experiment has queried Hydra for prior decisions.

4. **No BATS integration in experiment loop.** BATS exists in `providers/bats.py` and works standalone, but the crossover experiment doesn't use it to select models dynamically.

5. **No budget enforcement.** The genome has `max_usd`, `max_model_requests`, etc. but nothing in the harness actually enforces these limits during execution.

6. **DecisionPoint not logged per-task.** The experiment records results but doesn't create a `DecisionPoint` per task with candidate actions, predicted vs actual values.

## Provider Status

| Provider | Key | Status |
|----------|-----|--------|
| opencode-go | sk-fv9G... | Working (free tier) |
| groq | gsk_1J... | Key valid, models differ from expected (qwen3.8-27b, gpt-oss-20b, gpt-oss-120b) |
| openrouter | sk-or-v1-81... | Working (tested meta-llama/llama-3.1-8b-instruct) |
| cloudflare | cfat_Am... | Token stored (R2 storage) |

## What Needs Refinement

### Immediate (next session)
1. **Wire Letta harness into crossover.** Test: Direct vs Fast vs Letta-stateless on same 10 tasks.
2. **Add DecisionPoint logging.** Each task should produce a DecisionPoint with candidates, selected action, predicted cost, actual cost.
3. **Enforce budget limits.** `max_model_requests` and `max_usd` should abort runs that exceed them.
4. **Debug fs-05 Fast failure.** Check if thinking is actually disabled. Capture `reasoning_content` separately.

### Near-term
5. **Groq model routing.** Update BATS to use actual available models (qwen3.8-27b, gpt-oss-20b).
6. **Hydra projection.** After each run, project results into Hydra graph for empirical queries.
7. **Cost tracking.** Even at $0 for free tier, record cost_usd properly so paid models work automatically.

### YGO readiness
8. **Not ready yet.** The spec says: filesystem benchmarks FIRST, then YGO. We just did the first filesystem benchmark. Next steps:
   - More complex tasks (multi-file, debugging, code generation)
   - Letta stateful vs stateless comparison
   - Memory value experiment (does prior experience help?)
   - Then YGO World 001

## Raw Log

See `cross-1788166149.json` for full per-task results.
