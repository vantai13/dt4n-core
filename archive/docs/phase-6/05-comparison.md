# Lesson 6.5 — Detector comparison

## Registered reference points

The primary mask contains 590 rows: 160 positive and 430 negative. The
sensitivity mask removes two onset and two recovery ticks from each of eight
fault runs, leaving 558 rows: 144 positive and 414 negative. Under the primary
mask the recall ceilings are 95.0% for Isolation Forest and 97.5% for the
71-column envelope. Under the sensitivity mask both ceilings are 100%; all
detector-specific missing positive rows occur inside intervention transitions.

The always-normal baseline has 72.88% accuracy but zero recall. Accuracy is
therefore forbidden as a Phase 6 selection metric. On the 118 uninterrupted
control ticks, FPR is 0 for every envelope variant and averages 3.90% for the
registered IF configuration. Control-run FPR is the most stable operational
false-alarm measure because the normal portions of fault runs contain physical
recovery transients.

## Frozen operating points

All rows below preserve their registered primary/secondary status. In
particular, the successful excess rule is not relabelled as the primary rule.
Intervals are 95% cluster bootstrap intervals over run IDs.

| Detector | Primary recall (CI) | Primary FPR (CI) | Sensitivity recall (CI) | Sensitivity FPR (CI) | Control FPR | Primary delay / censored |
|---|---:|---:|---:|---:|---:|---:|
| Always normal | 0% | 0% | 0% | 0% | 0% | — / 8 |
| Envelope primary `k > 31` | 0% (0–0) | 0% (0–0) | 0% (0–0) | 0% (0–0) | 0% | — / 8 |
| IF q=0.01, five-seed mean | 0.13% | 2.37% | 0% | 2.22% | 3.90% primary | — / 7–8 |
| Loss-only | 54.38% (23.75–84.38) | 0.47% (0–1.16) | 56.94% (25–87.5) | 0% (0–0) | 0% | 1 / 3 |
| Envelope dual | 79.38% (54.38–98.13) | 0.47% (0–1.16) | 81.94% (56.94–100) | 0% (0–0) | 0% | 1 / 1 |
| Envelope excess | 85.63% (60.63–99.38) | 5.35% (2.33–8.37) | 87.50% (62.5–100) | 3.38% (0.72–5.80) | 0% | 0 / 1 |
| Excess OR IF | 85.63% | 6.28–6.51% | 87.50% | 4.35–4.59% | seed-dependent | 0 / 1 |
| Gaussian-noise IF control | 1.38% mean | 1.12% mean | not a registered arm | not a registered arm | 0.85% mean | exploratory delays only |

The mask change removes 11 excess true alarms and 9 false alarms, but also
removes 16 positive and 16 negative denominator rows. Excess recall therefore
rises by 1.88 points while FPR falls by 1.97 points. Dual removes all false
alarms and reaches precision 1.0 on this designed test. Precision is not a
deployment estimate because the 27.12% positive base rate is experimental.

## Contribution tables and Jaccard

The preregistration defines a primary comparison on all rows and a secondary
comparison on rows judgeable by both members. IF has eight unknown positive
ticks while the envelope has four; their common set contains 152 positive and
412 negative rows. The coverage difference matters: excess catches three
positive ticks outside the common set.

For excess versus IF, the five-seed positive cells on all 160 positives are:

| Seed | Both | Excess only | IF only | Both miss | Jaccard |
|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 137 | 0 | 23 | 0.0000 |
| 1 | 0 | 137 | 0 | 23 | 0.0000 |
| 2 | 0 | 137 | 0 | 23 | 0.0000 |
| 3 | 0 | 137 | 0 | 23 | 0.0000 |
| 4 | 1 | 136 | 0 | 23 | 0.0075 |

On the 152 common-judgeable positives, the corresponding cells are
`both=0, excess-only=134, IF-only=0, miss=18` for seeds 0–3 and
`1,133,0,18` for seed 4. IF adds no unique positive tick to excess in any
seed and adds four or five false positives. A near-zero Jaccard does not imply
useful complementarity: complementarity requires unique useful contribution
from both members. Disjoint feature identities are necessary at most, not
sufficient.

The preregistered `hybrid_or` did not name its envelope member. Under the
literal primary reading, `primary_k OR IF`, IF-only positives are
`0,0,0,0,1`; seed 0 has an empty detected-positive union, so Jaccard is null,
not zero. Under the secondary-excess reading, IF-only positives are zero in
all seeds. Both readings are reported; neither ambiguity is resolved after
seeing the result.

By fault for excess versus seed-0 IF on all positive rows, excess-only counts
are 40 admin-down, 19 degrade, 40 flood and 38 shift; the corresponding misses
are 0, 21, 0 and 2. IF-only is zero in every class.

## Per-channel witness attribution

The sensitivity mask gives the cleanest attribution because all 144 positive
rows are judgeable by every envelope variant.

| Rule | Admin down | Degrade | Flood | Shift | Total recall | FPR |
|---|---:|---:|---:|---:|---:|---:|
| Loss-only, eight `lossPct` columns | 0% | 27.78% | 100% | 100% | 56.94% | 0% |
| Dual indicator/rate rule | 100% | 27.78% | 100% | 100% | 81.94% | 0% |
| Normalised excess | 100% | 50.00% | 100% | 100% | 87.50% | 3.38% |
| IF, five seeds | 0% | 0% | 0% | 0% | 0% | 2.22% mean |

The rise from 56.94% to 81.94% is exactly 25 points and comes entirely from
admin-down. A down link carries no traffic and therefore need not report loss;
`state_up` supplies the witness that `lossPct` cannot. The next 5.56 points
come from one degrade run: rate channels cross at tick 22/23 while loss starts
at tick 31. Excess delay is one tick and loss-only delay is ten, confirming the
physical premise behind H2 even though H2 itself is refuted because its named
IF detector is censored.

The remaining 12.5 points are all 18 judgeable ticks of
`F-degrade-s1-s2`. Their excess is exactly zero on all 71 channels. This is a
measurement limit: no threshold on this statistic can recover rows whose
observations remain inside every learned bound.

The weighting mechanism explains the result. Thirty-five indicator channels
have zero training variance. Excess divides deviations by per-channel benign
range with floors of 0.1 for loss and 0.01 for state, whereas a throughput
channel can have a range around 400 kB/s. A zero-variance witness can therefore
receive a divisor up to 40 million times smaller than a rate channel. Count
gives each channel one vote, and IF cannot split constant columns at all;
normalised excess assigns the stable witnesses the weight their benign
variance warrants.

## Detection delay

Delay remains defined only on `eval_primary`, from tick 21. The metrics API
deliberately rejects delay under `eval_sensitivity`: removing onset ticks moves
the time origin to tick 23, so a reported zero would mean a different physical
latency and would not be comparable with the preregistered quantity.

Excess and excess-OR-IF have identical measured delay in every seed: median
zero among seven detected incidents and one censored low-intensity degrade
run. Per-run delays are `0,0,None,1,0,0,1,1`. Dual and loss-only have median
one; loss-only censors three incidents. Literal `primary_k OR IF` censors all
eight incidents for seeds 0–3 and seven for seed 4.

## Registered hypotheses

Ledger 3, SHA-256
`10c8be5fee6501cfcb208b9f408520e378251cd08d85e346770390b106fc5556`,
freezes all five hypotheses as refuted before hybrid exploration.

- **H1:** refuted at the registered operating points. The channel mechanism
  remains visible in dual recall 1.0 versus loss-only recall 0 on admin-down.
- **H2:** refuted because IF is censored. Its physical premise is independently
  supported by the registered excess/loss-only delay difference of nine ticks.
- **H3:** refuted. IF-only relative to the registered primary is
  `0,0,0,0,1`, below eight for every seed; relative to excess it is zero for
  every seed.
- **H4:** refuted because the envelope clause fails; the IF clause alone is
  supported.
- **H5:** refuted because the envelope control FPRs tie at zero; the IF clause
  alone is supported.

## Deviations and limitations

1. The registered primary rule `k > 31` has zero recall. Its status is
   unchanged. A varying-load held-out fold sets a threshold above every fault
   count, a calibration overshoot of the maximum order statistic.
2. `hybrid_or` is under-specified. Both the literal primary and secondary
   excess readings are reported.
3. `eval_sensitivity` was registered but not computed in Lessons 6.3–6.4. It
   is added here without changing scores or thresholds.
4. Both `K=31` and `E=8.968806` come from the one varying-configuration fold,
   so unseen-configuration calibration has an effective determining sample of
   one profile. Exploratory leave-one-run-out retains the other same-profile
   replicate and gives varying-run excess maxima 2.7897 and 3.9771. This
   measures within-profile repeatability and does not replace LOCO.

The common cause is a **load-diversity tax**. Diverse normal loads reduce
control-run false positives, but they widen the accepted rate envelope, own
the IF score tail, and inflate simultaneous count violations. The same normal
diversity appears as band-width masking for excess, tail inversion for IF, and
calibration overshoot for count.

## Ranking signal and operating utility

The Gaussian noise arm has mean AUC 0.5297 (SD 0.0239), while campaign IF seed
0 has AUC 0.8656 on equal coverage. IF therefore learns ranking signal. At the
registered q=1% point it has almost no recall because benign varying-load rows
extend farther into the anomalous tail than every fault row. Aggregate AUC and
low-FPR operating utility are separate claims.

## Recovery and Phase 7/8 handoff

Post-revert excess alarms last at most one tick for admin-down, two for
degrade, seven for flood and five for shift. Phase 8 should use a cooldown of
at least eight ticks. Phase 7 should expose `warming_up`, `unknown`, `normal`,
`suspect` and `alarm` states; treating NaN as normal would create
training-serving skew. Excess is the warning-level `suspect` signal. Dual is
the high-precision `act` signal. An 8 Mbps control run remains required before
claiming operation outside the calibrated load range.

## Artifacts

- `results/report/phase6_comparison.json`: five-seed contribution and hybrid delay.
- `results/report/phase6_sensitivity.json`: both registered masks and bootstrap intervals.
- `results/report/phase6_noise_auc.json`: real-versus-noise ranking diagnostic.
- `results/report/phase6_recovery.json`: post-revert spans and cooldown evidence.
- `results/report/phase6_envelope_loro_diag.json`: within-profile calibration stability.
