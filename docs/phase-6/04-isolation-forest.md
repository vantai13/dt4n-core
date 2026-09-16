# Lesson 6.4 — Isolation Forest

## Protocol and provenance

Isolation Forest uses the 72 frozen registered features: 36 raw/aggregate
features and their 36 first differences. Each CV fold refits `link_stats`, delta
features, and the forest using only fold-training rows. The five seeds, two
`max_samples` settings, four quantiles, and all hyperparameters remain exactly
as preregistered. The final 40 thresholds were computed and frozen in
`phase6_iforest_cv.json` before any test row was scored.

The IF train matrix contains 464 rows after the first delta row from each of
eight runs is removed. Effective lower-tail sample counts are 2.32, 4.64, 9.28,
and 23.20 for q = 0.005, 0.01, 0.02, and 0.05 respectively.

## Predictions recorded before the test stage

These predictions are derived from train-only cross-validation and frozen in
`results/report/phase6_hypothesis_ledger_2.json`, content SHA-256
`c6bb53440aca94a8f67fa479eefb39e8dd5d6309896b0288b9d537ce2b6b5d0b`,
before any campaign test row was scored.

### Held-out calibration

At q = 0.01, the mean held-out alarm rate is 0.00% on each fixed-load fold and
35.17% on the varying fold. Its five-seed range is 31.03%–37.07%; even the
lowest seed is 31 times the nominal q, so the conclusion does not depend on one
random state. No IF fold-training matrix contains a constant column. The blind
spot is therefore stable across folds, unlike the envelope, where 35 of 71
columns are constant in every fold-training set.

At q ≤ 0.02 all three fixed-load folds remain exactly 0.00%. At q = 0.05 the
2 Mbps and 1 Mbps folds show small mean rates of 0.17% and 0.34%, respectively;
the varying fold rises to 63.45%. Thus the varying-fold distribution has a deep
lower-tail cluster and a second moderate cluster rather than one uniform shift.

### One-directional coverage

Holding out a fixed load leaves the varying profile in fold training, and that
profile spans the fixed levels. Holding out the varying profile leaves only
constant-load runs, which do not span its levels or transitions. This is a
one-directional coverage relation, consistent with the mechanism registered
before CV.

The p95 of row-wise maximum absolute first difference is 401,683.8 on the
varying configuration and 24,943.0 across fixed configurations, a measured
**16.1× dynamics-extrapolation factor**. The varying fold therefore
extrapolates in dynamics as well as level; 36 of 72 features are first
differences.

### What 35.17% predicts

The 35.17% does **not** predict test FPR on `C-vary`. The varying fold is a
counterfactual where both normal varying runs are removed. The final test model
trains on all four configurations, including varying traffic, so `C-vary` is
interpolation for that model. The CV result predicts Phase 7 behavior when the
detector meets a traffic profile absent from training.

The directional test prediction remains: FPR on `C-vary` should exceed FPR on
`C-load2M`; no magnitude is attached to that prediction.

### Threshold ownership and expected recall cost

For every seed, all five rows below the strict q = 0.01 full-training threshold
belong to `normal_varying|vary`. They concentrate at transition-adjacent ticks,
including 16, 26, and 36–37. Benign load dynamics therefore owns the lower tail
that sets the operational threshold. Recall is expected to be lowest for fault
types with throughput signatures milder than a normal load step, particularly
`degrade`.

### Hypothesis bookkeeping

H4 remains **refuted**. Ledger 1 froze the overall decision from envelope
evidence, and its registered refutation condition says “either detector”; IF
evidence cannot reopen that decision. The IF clause alone is supported: the
varying fold is highest for every seed, and its minimum seed rate exceeds the
maximum of every other fold.

The disagreement identifies what each detector measures. Envelope count reacts
to how often a bound is crossed, peaking at the lowest load through an
order-statistics effect. IF score reacts to how far a row lies from the learned
manifold, peaking on the varying profile. No quantile, seed, hyperparameter, or
column was changed because of these observations.

## Frozen test results

The test stage was run once after the CV artifact and both ledgers were
committed. The test artifact content SHA-256 is
`a139e3973ce099ea68091c03194aadbe9b6c53fe25af5ba69987f1b1407b0283`.
The IF recall ceiling is 152/160 = 95.0% because 8 positive ticks are unknown.

At the primary configuration (`max_samples=256`, q=0.01), mean recall over
five seeds is **0.13%** (sample SD 0.28%, range 0–0.625%). Four seeds detect no
positive tick; seed 4 detects one `admin_down` tick. Mean FPR is **2.37%**
(SD 0.80%, range 1.63–3.72%). All eight incidents are censored for four seeds;
seven are censored for seed 4.

| q | Mean recall | Mean FPR | Recall range | FPR range |
|---:|---:|---:|---:|---:|
| 0.005 | 0.00% | 1.21% | 0–0% | 0.93–1.63% |
| 0.010 | 0.13% | 2.37% | 0–0.63% | 1.63–3.72% |
| 0.020 | 2.50% | 4.65% | 0.63–3.13% | 3.72–5.12% |
| 0.050 | 13.63% | 8.70% | 11.25–16.25% | 8.60–8.84% |

At q=0.01, `C-load2M` has FPR 0 for every seed while `C-vary` has mean FPR
7.80% (range 6.78–8.47%). The registered directional prediction is therefore
supported. The magnitude remains distinct from the counterfactual 35.17% CV
rate, exactly as recorded before test. Mean FPR is 3.90% on control runs and
1.79% on normal portions of fault runs.

The `max_samples=1.0` secondary setting gives zero recall for every seed at
q=0.01 and the same mean all-negative FPR of 2.37%. No feature is never split
across all five seeds under either setting.

## Noise control

The Gaussian noise arm uses the same 464×72 train and 590×72 test dimensions,
the same primary quantile and the campaign unknown mask. Its mean recall is
1.38% (range 0.63–1.88%) and mean FPR is 1.12%. The campaign IF's 0.13% recall
is lower than this control, while its FPR is higher. At the registered operating
point, these data provide no evidence that campaign IF learned a useful fault
ranking beyond the synthetic control.

## Plot inspection

![IF scores by test run](../../results/report/phase6_iforest_scores.png)

![Train and test score distributions](../../results/report/phase6_iforest_score_dist.png)

The fault windows and run ordering align with the frozen keys. Fault scores
mostly remain above the strict threshold. Low-score excursions occur primarily
in varying-load normal traffic and post-window transitions, matching the
train-only threshold-ownership diagnosis.

## Artifacts

- `results/report/phase6_iforest_cv.json`: train-only folds, 40 frozen thresholds, tail ownership and dynamics profile.
- `results/report/phase6_hypothesis_ledger_2.json`: append-only H4 clause decision and pre-test predictions.
- `results/report/phase6_iforest.json`: one-shot metrics, split usage and noise control.
- `results/report/phase6_iforest_ticks.csv`: primary seed-0 test scores and alarms.
- `results/report/phase6_iforest_scores.png`: inspected score timeline.
- `results/report/phase6_iforest_score_dist.png`: inspected train/test distributions.
