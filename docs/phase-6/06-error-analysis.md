# Lesson 6.6 — Error analysis and ablations

## Frozen ablation boundary

Predictions were frozen in `phase6_ablation_prereg.json`, SHA-256
`cd88d6095162b51c230388c2af25b829d2417d0c3c29b29c8e00e7928f68e4ad`,
at commit `886d818` before any A1–A3 fit. Original Phase 6 test results and the
A4 mask result were already known and declared. Seeds 0–4, q=0.01,
`max_samples=256`, metric code and unknown policy remained fixed. These are
exploratory mechanism tests and do not reopen H1–H5.

## Ablation results

| Ablation | Features | Mean recall | Mean FPR | Mean control FPR | Coverage / delay | Decision |
|---|---:|---:|---:|---:|---|---|
| Registered IF | 72 | 0.13% | 2.37% | 3.90% | ceiling 95%; mostly censored | reference |
| A1 drop all `d1.*` | 36 | 2.50% | 4.23% | 5.25% | ceiling 97.5%; median delay 8–10.5 when detected | **refuted** |
| A2 add causal `ma3` to IF | 108 | 0% | 3.02% | 4.58% | 16 unknown positive, 46 unknown negative; all incidents censored | **refuted** |
| A2 rolling 71-column excess | 71 | 76.88% | 8.14% | 0% | ceiling 92.5%; median delay 2; one censored | **refuted** |
| A3 raw without aggregates | 34 | 0% | 1.95% | 4.07% | ceiling 97.5%; all incidents censored | **supported** |

A1 predicted recall above 30%, fewer unknown rows, and lower control FPR.
Mean recall reaches only 2.5% and control FPR rises. Removing `d1` eliminates
first-difference priming NaNs, but it does not repair the global-density
ordering. Raw-feature missing counts are four positive and four negative, not
the preregistered 4/8; the prediction incorrectly assumed both reset-adjacent
negative ticks were missing in raw levels.

A2 confirms that causal smoothing delays the envelope: median delay rises from
zero to two ticks. It also reduces coverage and raises all-negative FPR from
5.35% to 8.14%, while control FPR remains zero. Its held-out varying fold still
owns `K=31` and sets a slightly larger `E=9.5935`. IF recall remains zero and
has no detected delay to compare. The conjunction is therefore refuted.

A3 supports the directional prediction: removing the two
`agg.rate_absz_*` channels lowers mean recall from A1's 2.5% to zero. The
effect is small in absolute usefulness but identifies the only IF channels
normalised relative to train link statistics as carrying detectable fault
signal.

A4 was completed before this preregistration. Moving from `eval_primary` to
`eval_sensitivity` changes envelope recall by only 1.9–2.6 points, reduces
excess FPR from 5.35% to 3.38%, and reduces dual FPR from 0.47% to zero.
Control FPR stays zero. The recall conclusion is robust; all-negative FPR is
sensitive to transition labelling.

## False-negative mechanisms

| Case | Rows | Mechanism | Numeric evidence |
|---|---|---|---|
| Low-intensity `degrade-s1-s2` | ticks 22–40 primary; 23–40 sensitivity | **Band-width masking** | excess is exactly 0 on all 71 channels; recorded maximum separation is 11.486, the weakest fault run |
| Degrade/shift intervention onset | envelope tick 21; IF ticks 21–22 | **Structured MNAR** | envelope has four and IF eight unknown positive rows; sensitivity removes all of them and both ceilings become 100% |
| `degrade-s2-s3` before loss appears | ticks 23–30 for dual/loss-only | **Channel delay** | excess delay 1 versus loss-only delay 10; eight judgeable rows separate rate from loss evidence |

The 12.5% sensitivity-mask miss rate is concentrated entirely in the 18 rows
of one run. Across the other seven fault runs, every one of 126 judgeable
positive rows is detected by excess. Both numbers must be reported together:
87.5% is the designed-test recall; 126/126 diagnoses where observable evidence
exists. The intervention label means a fault command was issued, not that a
measurable degradation necessarily followed.

No positive row has excess in `(0, E]`. Changing `E` anywhere within
`(0, 8.968806]` therefore leaves recall unchanged on this test and only moves
false positives. The 18 judgeable misses cannot be repaired by threshold
tuning because their excess is exactly zero.

## Recovery transients

Post-revert excess spans are at most one tick for admin-down, two for degrade,
seven for flood and five for shift. The ground-truth witness and the detector
answer different questions: ground truth follows the strongest registered
witness, while excess observes the union of 71 channels. Both measurements can
be correct. The controller should use the detector-wide value and enforce a
cooldown of at least eight ticks to avoid treating residual recovery state as
a new fault.

## Lessons for the next data round

Normal-load diversity creates a measured tradeoff. It gives zero control FPR
for envelope rules, yet masks a weak rate-only fault, owns the IF tail, and
sets both count and excess calibration through one varying profile. Future
data should add independent varying-load replicates, an 8 Mbps control, and
multiple degrade intensities around the observability boundary. New rules must
be preregistered and evaluated on new data rather than tuned on these ten test
runs.

## Artifacts

- `results/report/phase6_ablation_prereg.json`: predictions frozen before A1–A3.
- `results/report/phase6_ablations.json`: five-seed results and decisions.
- `results/report/phase6_recovery.json`: per-run post-revert alarms.
- `results/report/phase6_sensitivity.json`: registered mask analysis.
