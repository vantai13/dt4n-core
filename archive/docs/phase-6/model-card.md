# Model card — DT4N envelope detector, Phase 6

## Intended function

The detector performs one-class anomaly detection on 71 network telemetry
channels. It learns finite min/max bounds from 472 normal rows spanning four
load configurations. The excess rule sums per-channel normalised bound
violations; the dual rule separates stable indicator witnesses from shared
rate channels.

## Recommended operating points

- **Warning / `suspect`:** normalised excess. On `eval_sensitivity`, recall is
  87.5%, FPR is 3.38%, control FPR is 0%, precision on the designed test is
  0.90, and primary-mask median delay is zero.
- **Action / `act`:** dual rule. Recall is 81.94%, FPR and control FPR are 0%,
  precision is 1.0 on this test, and primary-mask median delay is one tick.

These roles reflect different costs. A warning changes a dashboard state; an
action can change routing. Precision depends on the designed 27.12% base rate
and is not a deployment estimate.

## Known failure modes

1. A weak rate-only fault can remain inside every global bound. The
   `degrade-s1-s2` run has excess exactly zero on all 18 judgeable sensitivity
   rows and the smallest recorded separation, 11.486.
2. Isolation Forest excludes 35 stable indicator channels from its frozen
   feature set. Constant columns also cannot be split by its trees. It does
   not provide useful coverage for loss/down faults at q=1%.
3. Count `k > K` is unusable here: unseen valid varying load reaches 31
   violations while fault rows reach at most 22.
4. Calibration covers 1, 2, 4 Mbps and two varying-load runs. Behavior outside
   this support, including 8 Mbps, is unverified and likely to raise rate
   alarms.
5. `K` and `E` are both determined by the one held-out varying configuration.
   Leave-one-run-out gives same-profile varying maxima 2.7897 and 3.9771 but
   does not estimate unseen-profile uncertainty.
6. Flood and shift leave residual alarms for three to seven ticks after
   revert. These are recovery transients across the 71-channel union.
7. Causal rolling reduces coverage, delays detection and increases
   all-negative FPR in this campaign; it is not a drop-in repair.

## Threshold sensitivity

No positive row has excess in `(0, 8.968806]`. Every threshold in that
interval gives the same measured recall; it changes false positives only.
Rows with excess zero are outside the capability of threshold adjustment.

## Missing data and serving states

Under `eval_primary`, recall ceilings are 95% for IF and 97.5% for envelope.
Under `eval_sensitivity`, both are 100%, showing that positive missingness is
confined to intervention transitions. Runtime serving must expose
`warming_up` and `unknown` states. Mapping missing data to `normal` would
create training-serving skew and invalidate this evaluation.

## Uncertainty

There are ten test runs. Cluster-bootstrap intervals are consequently wide:
primary excess recall is 60.6–99.4%, and sensitivity excess recall is
62.5–100%. Per-fault confidence intervals are not claimed because each class
has only two runs.

## Recovery and control integration

Use at least an eight-tick cooldown after network configuration changes.
`excess` may enter `suspect`; only the higher-precision dual rule should permit
an action. State exit should use separate hysteresis and must not occur during
`unknown` or cooldown.

## Unsupported uses

- Claims about physical networks beyond this single-host Mininet topology.
- Loads outside the calibrated range without new controls.
- Automatic remediation from excess alone.
- Replacing the registered primary result with a post-result secondary rule.

## Reproducibility and provenance

Thresholds, five seeds, unknown policy, bootstrap seed and all registered
decisions are bound by SHA-addressed JSON artifacts. The Phase 6 manifest
records source/result hashes and registration commit order. Tick-level CSVs
allow every point metric to be recalculated without fitting a detector.
