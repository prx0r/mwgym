# MWGym Experiment Review

Generated: 2026-08-31T10:10:28Z
Experiments reviewed: 6

---

## crossover-direct-vs-fast

- Run ID: `cross-1788166149`
- Timestamp: 2026-08-31T08:51:48Z
- Tasks: 10
- Winner: **direct-fast**

### Genome Performance

| Genome | Pass | Tokens (avg) | Latency (avg) | Artifacts | Failures |
|--------|------|-------------|---------------|-----------|----------|
| direct-fast | 10/10 (100%) | 64 | 6863ms | 0 | 0 |
| fast-bundle | 9/10 (90%) | 216 | 9109ms | 9 | 1 |

### Failures: fast-bundle

- `fs-05`: timeout — The read operation timed out

---

## crossover-v2-direct-fast-router

- Run ID: `cross-1788167671`
- Timestamp: 2026-08-31T09:17:37Z
- Tasks: 10
- Winner: **D-router**

### Genome Performance

| Genome | Pass | Tokens (avg) | Latency (avg) | Artifacts | Failures |
|--------|------|-------------|---------------|-----------|----------|
| D-router | 10/10 (100%) | 117 | 5974ms | 3 | 0 |
| direct-fast | 9/10 (90%) | 70 | 6210ms | 0 | 1 |
| fast-bundle | 9/10 (90%) | 198 | 6442ms | 10 | 1 |

### Failures: direct-fast

- `fs-04`: wrong_output — 1, 2, 3

### Failures: fast-bundle

- `fs-08`: wrong_output — ```json
{
    "status": "complete",
    "writes": [
        {
            "path"

---

## crossover-v2-direct-fast-router

- Run ID: `cross-1788170853`
- Timestamp: 2026-08-31T10:10:28Z
- Tasks: 10
- Winner: **direct-fast**

### Genome Performance

| Genome | Pass | Tokens (avg) | Latency (avg) | Artifacts | Failures |
|--------|------|-------------|---------------|-----------|----------|
| C-letta-stateless | 9/10 (90%) | 140 | 3997ms | 8 | 1 |
| D-router | 10/10 (100%) | 108 | 4474ms | 3 | 0 |
| direct-fast | 10/10 (100%) | 61 | 3739ms | 0 | 0 |
| fast-bundle | 9/10 (90%) | 192 | 5355ms | 10 | 1 |

### Failures: fast-bundle

- `fs-08`: wrong_output — ```json
{
  "status": "complete",
  "writes": [
    {
      "path": "README.md",

### Failures: C-letta-stateless

- `fs-08`: wrong_output — {
  "status": "complete",
  "writes": [
    {
      "path": "README.md",
      "

---

## ygo-genome-allocation

- Run ID: `ygo-1788169300`
- Timestamp: 2026-08-31T09:41:40Z
- Tasks: 30
- Winner: **wg-static**

### Genome Performance

| Genome | Pass | Tokens (avg) | Latency (avg) | Artifacts | Failures |
|--------|------|-------------|---------------|-----------|----------|
| wg-memory | 0/10 (0%) | 0 | 0ms | 0 | 10 |
| wg-memory-bats | 0/10 (0%) | 0 | 0ms | 0 | 10 |
| wg-static | 0/10 (0%) | 0 | 0ms | 0 | 10 |

### Failures: wg-static

- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 

### Failures: wg-memory

- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 

### Failures: wg-memory-bats

- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 

---

## ygo-genome-opponent-matrix

- Run ID: `ygo-1788169828`
- Timestamp: 2026-08-31T09:50:28Z
- Tasks: 120
- Winner: **wg-static**

### Genome Performance

| Genome | Pass | Tokens (avg) | Latency (avg) | Artifacts | Failures |
|--------|------|-------------|---------------|-----------|----------|
| wg-memory | 0/40 (0%) | 0 | 0ms | 0 | 40 |
| wg-memory-bats | 0/40 (0%) | 0 | 0ms | 0 | 40 |
| wg-static | 0/40 (0%) | 0 | 0ms | 0 | 40 |

### Failures: wg-static

- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 

### Failures: wg-memory

- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 

### Failures: wg-memory-bats

- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 

---

## ygo-genome-opponent-matrix

- Run ID: `ygo-1788170509`
- Timestamp: 2026-08-31T10:01:49Z
- Tasks: 120
- Winner: **wg-static**

### Genome Performance

| Genome | Pass | Tokens (avg) | Latency (avg) | Artifacts | Failures |
|--------|------|-------------|---------------|-----------|----------|
| wg-memory | 0/40 (0%) | 0 | 0ms | 0 | 40 |
| wg-memory-bats | 0/40 (0%) | 0 | 0ms | 0 | 40 |
| wg-static | 0/40 (0%) | 0 | 0ms | 0 | 40 |

### Failures: wg-static

- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 

### Failures: wg-memory

- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 

### Failures: wg-memory-bats

- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 
- `None`: wrong_output — 

---

## Recommendations

1. FIX: fast-bundle timed out on fs-05 — increase max_wall_seconds or reduce context_pack size for fast-bundle genome
2. OPTIMIZE: fast-bundle uses 3.4x more tokens than direct-fast — consider shorter system prompts or fewer output fields
3. RELIABILITY: fast-bundle at 90% pass rate — investigate 1 failure(s)
4. OPTIMIZE: fast-bundle uses 2.8x more tokens than direct-fast — consider shorter system prompts or fewer output fields
5. RELIABILITY: direct-fast at 90% pass rate — investigate 1 failure(s)
6. RELIABILITY: fast-bundle at 90% pass rate — investigate 1 failure(s)
7. OPTIMIZE: fast-bundle uses 3.1x more tokens than direct-fast — consider shorter system prompts or fewer output fields
8. RELIABILITY: fast-bundle at 90% pass rate — investigate 1 failure(s)
9. RELIABILITY: C-letta-stateless at 90% pass rate — investigate 1 failure(s)
10. RELIABILITY: wg-static at 0% pass rate — investigate 10 failure(s)
11. RELIABILITY: wg-memory at 0% pass rate — investigate 10 failure(s)
12. RELIABILITY: wg-memory-bats at 0% pass rate — investigate 10 failure(s)
13. RELIABILITY: wg-static at 0% pass rate — investigate 40 failure(s)
14. RELIABILITY: wg-memory at 0% pass rate — investigate 40 failure(s)
15. RELIABILITY: wg-memory-bats at 0% pass rate — investigate 40 failure(s)
16. RELIABILITY: wg-static at 0% pass rate — investigate 40 failure(s)
17. RELIABILITY: wg-memory at 0% pass rate — investigate 40 failure(s)
18. RELIABILITY: wg-memory-bats at 0% pass rate — investigate 40 failure(s)
19. NEXT STEP: Both baseline genomes validated. Build the dynamic router (Arm D) that picks direct-fast for simple tasks and fast-bundle for multi-file tasks
20. LETTA HARNESS: Not yet benchmarked. Need letta-stateless and letta-stateful arms to complete the 4-arm crossover from MWGYM-V2-SPEC
