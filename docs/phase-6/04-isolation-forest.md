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

Pending the one-shot test stage.
