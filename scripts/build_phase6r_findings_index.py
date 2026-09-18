#!/usr/bin/env python3
"""Index every Phase 6R finding so a recorded observation cannot be forgotten.

Three times in Phase 6R an observation was written down and then not linked to
later work: F-6R4-1 (6R.4, resurfaced as the S11 failure in 6R.6), the probe v2
QUEUE_THEN_DROP mass balance (6R.3, resurfaced as an 'unknown mechanism' in
6R.7), and the LinkDegrade floor (6R.1, remembered). The pin ledger tracks SHA
drift; this index does the same for findings. test/test_phase6r_findings_index
requires every finding to be cited, by its anchor, in a document other than
the one where it was recorded.
"""
from __future__ import annotations

import json
import sys

from ml import campaign as C

OUT = C.ROOT / "results/report/phase6r_findings_index.json"
PREREG = "results/report/phase6r_acceptance_prereg.json"
CARD = "docs/phase-6r/model-card-v2.md"

STATUSES = {
    "MO TA": "observed and recorded, not yet explained",
    "DA GIAI THICH": "mechanism established, not yet used by a decision or prediction",
    "DA DUNG DEN": "used by a registered decision or prediction",
}

FINDINGS = [
    {
        "id": "F-6R4-1",
        "lesson": "6R.4",
        "source": "results/report/phase6r_amendment_3.json",
        "anchor": "finding_F_6R4_1_plan",
        "summary": "evidence outside the routing zone after revert (link-s2-s3)",
        "status": "MO TA",
        "status_note": "the INJECT window was explained by amendment 7 (detour corridor); the POST-REVERT window that F-6R4-1 actually observed is untested",
        "referenced_by": [PREREG, CARD],
    },
    {
        "id": "QUEUE_THEN_DROP",
        "lesson": "6R.3",
        "source": "docs/phase-6r/01f-sensor-probe-v2-results.md",
        "anchor": "QUEUE_THEN_DROP",
        "summary": "degrade fills the netem queue before any drop; mass balance closes on C0 and C2",
        "status": "DA DUNG DEN",
        "status_note": "used by rho_and_the_residual_mechanism: residual measures queue accumulation",
        "referenced_by": [PREREG],
    },
    {
        "id": "C1_WITHHELD",
        "lesson": "6R.3",
        "source": "docs/phase-6r/01f-sensor-probe-v2-results.md",
        "anchor": "SENSOR_CORRECT_ON_S1S2",
        "summary": "s1-s2 with offload on: closure 0.9221/0.9108, qlen 980/970 < 995, conclusion withheld by the sealed rule",
        "status": "MO TA",
        "status_note": "the R-campaign condition for five R-D runs; not upgraded after the fact",
        "referenced_by": [PREREG, CARD],
    },
    {
        "id": "GSO_DELAYED_DROP",
        "lesson": "6R.3",
        "source": "docs/phase-6r/01f-sensor-probe-v2-results.md",
        "anchor": "GSO_EXPLAINS_DELAYED_DROP",
        "summary": "offload changes skb size ~2x and so the queue's byte capacity and the drop time",
        "status": "DA DUNG DEN",
        "status_note": "used by overflow_s predictions and by environment_facts_not_pinned_in_sidecars",
        "referenced_by": [PREREG],
    },
    {
        "id": "LINKDEGRADE_FLOOR",
        "lesson": "6R.1",
        "source": "results/report/phase6r_amendment_1.json",
        "anchor": "r_d_design_correction",
        "summary": "LinkDegrade clamps new_bw at 1.0 Mbps; sealed factors collided",
        "status": "DA DUNG DEN",
        "status_note": "corrected factors for R-D; explains delivered capacity 1.0 on Phase 5 s2-s3",
        "referenced_by": [PREREG],
    },
    {
        "id": "RESIDUAL_DILUTION",
        "lesson": "6R.7",
        "source": PREREG,
        "anchor": "dilution_model",
        "summary": "r ~= (offered - capacity) / switch inflow; effective thresholds 1.138 (s1-s2) and 1.319 (s2-s3)",
        "status": "DA DUNG DEN",
        "status_note": "drives the per-cell R-D predictions, including the predicted s2-s3 rho125 miss",
        "referenced_by": [CARD],
    },
    {
        "id": "HIGH_LOAD_SPECIFICITY_GAP",
        "lesson": "6R.7",
        "source": PREREG,
        "anchor": "declared_coverage_gap",
        "summary": "high-load residual false alarms are covered only by the report-only S10",
        "status": "MO TA",
        "status_note": "carried to Phase 7; not repaired inside 6R",
        "referenced_by": [CARD],
    },
    {
        "id": "S1S2_MISFIT_VS_C1",
        "lesson": "6R.7",
        "source": PREREG,
        "anchor": "C1_and_the_s1s2_misfit_cannot_both_be_innocent",
        "summary": "dilution model misfits s1-s2 by +10.9% in rate-based in-out; either the C1 hole is in qdisc reporting or in byte counters, not both",
        "status": "MO TA",
        "status_note": "two mutually exclusive hypotheses registered; the diagnostic cell s2-s3 rho125 does not depend on the answer",
        "referenced_by": [CARD],
    },
    {
        "id": "RELEASE_SCOPE_2M",
        "lesson": "6R.7",
        "source": PREREG,
        "anchor": "release_scope_restriction_not_a_new_gate",
        "summary": "every gated R-campaign group runs at 2 Mbps per client; a release claim is held to that load",
        "status": "DA DUNG DEN",
        "status_note": "restricts the amendment 1 all_pass release claim without adding a gate",
        "referenced_by": [CARD],
    },
    {
        "id": "OFFLOAD_UNPINNED",
        "lesson": "6R.7",
        "source": PREREG,
        "anchor": "environment_facts_not_pinned_in_sidecars",
        "summary": "offload state changes drop timing and is recorded in no sidecar",
        "status": "MO TA",
        "status_note": "Phase 7 must check ethtool -k before comparing drop counts",
        "referenced_by": [CARD],
    },
]


def main() -> int:
    content = {"index_id": "DT4N-P6R-FINDINGS", "statuses": STATUSES, "findings": FINDINGS}
    C.atomic_json(OUT, {"content": content,
                        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode())})
    print("[6R-FINDINGS] %d findings, content_sha256 = %s"
          % (len(FINDINGS), json.loads(OUT.read_text())["content_sha256"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
