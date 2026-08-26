# Factor-A mechanism audit: final six-seed Nano matrix

## Scope

- 80 Retail tasks × 6 seeds = **480 paired C1–C0 cells**.
- A is isolated through **C1 Semantic Support versus C0 Native**.
- The audit separates source fidelity, card delivery, write opportunity and paired outcome.
- A write linkage means that the card was active when the native agent proposed a write. It does **not** prove that the hidden model reasoning used the card.

## Mechanism integrity

| Check | Result |
|---|---:|
| C1 cells | 480 |
| cells with at least one A opportunity | 458 |
| cells with an activated card | 360 |
| cells with an injected card | 360 |
| cells with a card active at a write candidate | 318 |
| cross-turn cards | 345 |
| trace audits passed | 480/480 |
| accepted card fields independently rechecked against cited user text | 7807/7807 |
| linked-card fields independently rechecked | 3858/3858 |
| cells with rejected extraction records | 315 |
| cells with fail-open events | 11 |
| linked candidate operation agrees with active card operation | 296/318 |
| linked candidate operation is a benchmark-expected write type | 308/318 |
| linked cards containing at least one expected operation | 310/318 |
| linked cards covering every expected operation | 292/318 |
| linked cards containing only expected operations | 122/318 |
| linked cards containing additional operation hypotheses | 196/318 |
| comparable linked identifier fields matching benchmark writes | 683/938 |

## Paired DB-Match outcomes

| Mechanism stratum | Cells | Saved | Broken | Net | Saved among discordant |
|---|---:|---:|---:|---:|---:|
| All cells | 480 | 78 | 49 | +29 | 61.4% |
| No card | 120 | 12 | 13 | -1 | 48.0% |
| Card, no write linkage | 42 | 4 | 9 | -5 | 30.8% |
| Card with write linkage | 318 | 62 | 27 | +35 | 69.7% |
| Linked, operation concordant | 122 | 21 | 9 | +12 | 70.0% |
| Linked, operation not concordant | 196 | 41 | 18 | +23 | 69.5% |
| Cross-turn card | 345 | 61 | 36 | +25 | 62.9% |
| Single-turn card | 15 | 5 | 0 | +5 | 100.0% |
| At least one rejected record | 315 | 58 | 34 | +24 | 63.0% |
| No rejected record | 165 | 20 | 15 | +5 | 57.1% |
| Both C0 and C1 wrote | 366 | 50 | 33 | +17 | 60.2% |
| Both wrote, card write-linked | 294 | 43 | 26 | +17 | 62.3% |
| Both wrote, card not write-linked | 72 | 7 | 7 | +0 | 50.0% |

## Paired Exact-Mutation outcomes

This endpoint uses only the 432 task-seed cells with a mutation oracle.

| Mechanism stratum | Cells | Saved | Broken | Net | Saved among discordant |
|---|---:|---:|---:|---:|---:|
| All cells | 432 | 73 | 46 | +27 | 61.3% |
| No card | 92 | 11 | 12 | -1 | 47.8% |
| Card, no write linkage | 24 | 1 | 9 | -8 | 10.0% |
| Card with write linkage | 316 | 61 | 25 | +36 | 70.9% |
| Linked, operation concordant | 122 | 20 | 9 | +11 | 69.0% |
| Linked, operation not concordant | 194 | 41 | 16 | +25 | 71.9% |
| Cross-turn card | 327 | 57 | 34 | +23 | 62.6% |
| Single-turn card | 13 | 5 | 0 | +5 | 100.0% |
| At least one rejected record | 295 | 53 | 31 | +22 | 63.1% |
| No rejected record | 137 | 20 | 15 | +5 | 57.1% |
| Both C0 and C1 wrote | 365 | 50 | 32 | +18 | 61.0% |
| Both wrote, card write-linked | 294 | 43 | 25 | +18 | 63.2% |
| Both wrote, card not write-linked | 71 | 7 | 7 | +0 | 50.0% |

## Distribution across seeds

The table reports the net number of saved minus broken DB-Match cells. A write-linked card is non-negative in every seed, whereas the overall result turns negative in seed 976306 because of cells without write linkage.

| Seed | All C1 cells | Write-linked | Not write-linked |
|---|---:|---:|---:|
| 976301 | +7 | +6 | +1 |
| 976302 | +7 | +8 | -1 |
| 976303 | +2 | +0 | +2 |
| 976304 | +9 | +9 | +0 |
| 976305 | +9 | +12 | -3 |
| 976306 | -5 | +0 | -5 |

Among discordant DB-Match cells, the odds of a saved rather than broken result are 3.16 times as high with write linkage as without it (two-sided Fisher test: p = 0.0051). For Exact Mutation, the corresponding descriptive odds ratio is 4.27 (p = 0.0007). These are post-treatment associations and therefore mechanism evidence, not causal effect estimates.

## Interpretation boundary

The audit can establish that the mechanism produced source-faithful content, injected it, and exposed it at a relevant decision point. It can also show whether outcome switches are concentrated in those opportunities. It cannot observe the model's hidden causal reasoning. Moreover, card activation and write linkage are post-treatment variables: their strata support mechanism plausibility, not a new randomized causal contrast.

Benchmark-operation concordance is intentionally separate from source fidelity. The deterministic gate verifies that accepted field values occur in cited user messages; the operation label itself is chosen semantically by the support model and may disagree with the benchmark's expected transaction.
