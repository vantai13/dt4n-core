#!/usr/bin/env python3
"""Register the Phase 6R acceptance analysis before the R-set is opened.

Nothing here reads R-campaign snapshots.  Every number quoted from data comes
from Phase 5/6, which has been open since Phase 6, and every such number is
labelled with its source run so a reader can recompute it.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from ml import campaign as C

REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_acceptance_prereg.json"

CODE = (
    "ml/model.py", "ml/serve.py", "ml/serve_fast.py", "ml/fsm.py",
    "ml/oscillation.py", "ml/blast_radius.py", "ml/intervention_log.py",
    "ml/conservation.py", "ml/labels.py", "ml/campaign.py", "ml/payload.py",
    "ml/features.py", "ml/flatten.py", "ml/missing.py",
    "ml/snapshot_contract.py", "ml/rcampaign.py", "ml/replay_guard.py",
    "ml/acceptance_stats.py", "ml/acceptance_guard.py", "ml/acceptance_pass.py",
)


def _content_sha(name: str) -> str:
    return json.loads((REPORT / name).read_text(encoding="utf-8"))["content_sha256"]


def main() -> int:
    content = {
        "prereg_id": "DT4N-P6R-ACCEPTANCE",
        "lesson": "6R.7",
        "purpose": "fix every analysis decision before the R-set is opened once",

        "amends": {
            "slo_content_sha256": _content_sha("phase6r_slo.json"),
            "amendment_1_content_sha256": _content_sha("phase6r_amendment_1.json"),
            "amendment_2_content_sha256": _content_sha("phase6r_amendment_2.json"),
            "amendment_3_content_sha256": _content_sha("phase6r_amendment_3.json"),
            "amendment_4_content_sha256": _content_sha("phase6r_amendment_4.json"),
            "amendment_5_content_sha256": _content_sha("phase6r_amendment_5.json"),
            "amendment_6_content_sha256": _content_sha("phase6r_amendment_6.json"),
            "amendment_7_content_sha256": _content_sha("phase6r_amendment_7.json"),
            "stability_v2_content_sha256": _content_sha("phase6r_stability_v2.json"),
            "equivalence_content_sha256": _content_sha("phase6r_equivalence.json"),
            "tick_jitter_content_sha256": _content_sha("phase6r_tick_jitter.json"),
            "fsm_content_sha256": _content_sha("phase6r_fsm.json"),
            "rcampaign_manifest_file_sha256": C.sha256_file(
                REPORT / "phase6r_rcampaign_manifest.json"
            ),
        },

        # ------------------------------------------------ superseded statements
        "supersession_ledger": [
            {
                "superseded": "phase6r_amendment_3.finding_F_6R4_1_plan.status",
                "text": "MO TA; khong doi dinh nghia vung, khong doi luat uc che trong 6R",
                "superseded_by": "amendment 7 (content_sha256 %s)" % _content_sha(
                    "phase6r_amendment_7.json"
                ),
                "what_changed": "the ZONE DEFINITION: radius() -> radius_with_detour(); the zone for admin_down s1-s2 grows from 11 to 14 entities (adds link-s1-s3, link-s2-s3, switch-s3)",
                "what_did_NOT_change": "the SUPPRESSION RULE. local <= zone stands and was not weakened to local & zone. Amendment 3 forbade two things; amendment 7 crossed exactly one of them.",
                "why": "S11 was a sealed FAIL on both RO-ctl runs. Under failure_protocol, repairing the cause is the only available path; loosening the suppression rule is forbidden.",
                "declared_late": True,
                "note": "amendment 7 amends references only amendment 6 and stability v1, and does NOT reference this statement of amendment 3. Recorded here. The amendment chain is hash-linked (a3->a4->a5->a6), but a superseded statement does not surface in that chain by itself: this is a PROCESS gap, not an evidence gap.",
            },
            {
                "registered_hypothesis_refuted": {
                    "source": "phase6r_amendment_3.finding_F_6R4_1_plan.hypothesis_to_test_later",
                    "hypothesis": "lien ket qua tai nguyen dung chung (CPU/kernel Mininet) ngoai routing",
                    "verdict": "REFUTED FOR THE INJECT WINDOW; UNTESTED FOR THE POST-REVERT WINDOW",
                    "scope_correction": "F-6R4-1 observed the POST-REVERT window (link brought back up). H2 of amendment 7 observed the window while INJECT WAS STILL ACTIVE (link down). Same entity link-s2-s3, adjacent mechanism, NOT the same phenomenon. The refutation claim is held to the window that has direct evidence.",
                    "actual_mechanism": "the routing detour corridor s1-s3-s2. radius() answers 'which flows currently traverse this link' from the frozen routing table, so it follows pre-action routes through s1-s2 and omits the physical alternate path. Blast radius is a COUNTERFACTUAL quantity; radius() answered it by observing the present state, so it answered the wrong question.",
                    "evidence": "scripts/diag_s11_suppression.py (sha256 f69802c81a704a06c0e3cc8ab99dac92951da361ed3fc1fe6295045ebb404a2e): link-s2-s3 outside the zone from tick 21, link-s1-s3 from tick 22, same order on seeds 4301 and 4302; the one-tick offset matches topology distance (s2 is directly affected, s1-s3 is one hop further).",
                    "why_this_is_a_result_not_a_mistake": "the mechanism was registered at amendment 3 BEFORE the answer was known, in terms specific enough to be wrong. The data refuted it and identified the true mechanism. A correct guess would say less about process quality, because a vague guess can never be wrong.",
                    "discriminating_power_is_WEAK_and_must_be_stated": "the topology has 16 entities (5 hosts + 3 switches + 8 links). The amended zone contains 14 of them. So local <= zone holding on 21/21 ticks excludes only host-srv2 and link-s3-srv2. That is WEAK evidence for 'routing rather than shared resources': a CPU/kernel contention mechanism would also fall inside 14/16 entities most of the time. The STRONG evidence for the routing mechanism is the tick 21/22 diagnosis and its reproduction on two seeds, NOT the 21/21 suppression ratio.",
                    "still_open": "the mechanism of the POST-REVERT window. Amendment 3 directs it to R-C and R-O. Current belief: also routing (re-convergence when the link returns), but there is no direct evidence yet.",
                },
            },
            {
                "affected_gate": "G2",
                "text": "act-level FP events == 0 tren R-C khi co InterventionLog (lien quan F-6R4-1)",
                "impact": "G2 is measured WITH InterventionLog, so it depends on the zone definition. The zone grew from 11/16 to 14/16 entities, so suppression is easier and G2 is EASIER TO PASS than when it was registered.",
                "commitment": "report G2 under BOTH zones: the original radius() and radius_with_detour(). R-C has role HIEU CHINH, so it may be measured repeatedly and neither number spends the single-open budget of the R-set.",
                "why_disclose": "reporting only the new-zone number would let G2 pass because of a change made AFTER S11 was known to fail. Reporting both turns a process weakness into a measurement.",
            },
            {
                "declaration_did_not_match_implementation": {
                    "planned": "amendment 7 planned_changes: scripts/replay_phase6r_stability.py -- 'for v2 only, reconstruct amended admin_down radius from sealed targets'",
                    "implemented": "the original file was not changed by a single byte (it still matches the pin in phase6r_stability.json); scripts/replay_phase6r_s11_v2.py was added instead",
                    "direction": "STRICTER than planned, not looser: additive rather than mutative, so the older receipt still reproduces",
                    "note": "recorded so a reader comparing planned_changes against the diff does not have to wonder",
                },
            },
        ],

        # -------------------------------------------------- frozen configuration
        "frozen_configuration": {
            "artifact": {
                "file": "models/envelope-1.0.0.json",
                "content_sha256": json.loads(
                    (C.ROOT / "models/envelope-1.0.0.json").read_text(encoding="utf-8")
                )["content_sha256"],
            },
            "conservation": {
                "source": "phase6r_amendment_1.json",
                "R": 0.0796613817054327,
                "floor_bps": 10000.0,
                "R_owner": {
                    "run_id": "N-vary-s1008-r2", "tick": 6, "switch": "s1",
                    "config_id": "normal_varying|vary",
                },
                "rule": "alarm iff judgeable and r_max > R (strict, one-sided)",
            },
            "fsm_params": {"n_suspect": 1, "n_act": 2, "release_m": 3, "cooldown_s": 8.0},
            "scorer": "ml.serve_fast.FastOnlineScorer",
            "scorer_justification": "S5 p95 = 0.943 ms (phase6r_latency_v2); the reference OnlineScorer measured p95 = 56.249 ms and would FAIL S5. Bit-exact equivalence 1062/1062 rows is pinned in phase6r_equivalence.json.",
            "suppression_radius": "ml.blast_radius.radius_with_detour (amendment 7)",
            "suppression_rule": "local <= zone, unchanged",
            "code_sha256": {path: C.sha256_file(C.ROOT / path) for path in CODE},
            "freeze_tag": "phase-6r-frozen",
            "environment_facts_not_pinned_in_sidecars": {
                "offload_state": {
                    "value_at_collection": "OS default (on), inferred: no script in the R-campaign pipeline calls ethtool; only scripts/probe_degrade_sensor.py and scripts/analyze_degrade_sensor_probe_v2.py touch offload",
                    "why_it_matters": "probe v2 (01f) GSO_EXPLAINS_DELAYED_DROP: skb ~2.85 kB with offload on against ~1.49 kB off changes the queue's byte capacity by about 2x, and so changes when drops begin",
                    "affects": ["n_ticks_with_qdisc_drop on R-D", "the S4 evidence-clock column", "overflow_s predictions"],
                    "does_NOT_affect": "backlog accumulation and therefore the residual, which counts bytes, not packets. The residual is the indicator LESS dependent on this environment fact, and that is a mechanical argument in its favour.",
                    "verification_for_phase7": "ethtool -k <intf> | grep -E 'tcp-segmentation|generic-(segmentation|receive)' before comparing any drop count with 6R",
                    "not_retrofitted": "sealed sidecars are not regenerated; recorded here",
                },
            },
        },

        # ---------------------------------------------------------- the channels
        "channels": {
            "n_fsm_channels": 2,
            "n_tick_level_channels": 1,
            "fsm_channels": [
                {"id": "envelope_only",
                 "suspect": "reading.envelope_suspect",
                 "act": "reading.act (dual rule of envelope-1.0.0)"},
                {"id": "combined",
                 "suspect": "reading.envelope_suspect OR reading.cons_alarm",
                 "act": "reading.act (unchanged, amendment 1 combination.act)"},
            ],
            "tick_level_channels": [
                {"id": "residual_only",
                 "alarm_per_tick": "reading.cons_judgeable AND reading.cons_r_max > R",
                 "has_fsm": False,
                 "used_for": ["P1", "P2", "P3", "F1", "F2", "F3", "F4", "F5"]},
            ],
            "residual_only_has_no_fsm": True,
            "why_no_fsm_for_residual": "amendment 1 combination.act reads 'khong doi: dual rule cua envelope-1.0.0'. The residual channel has NO registered act rule. Giving it a DetectorFSM would force inventing an unregistered act rule, which is adding a second variant after seeing the numbers through a back door. F1-F5 and P1-P3 are all TICK-LEVEL quantities and need no FSM.",
            "derivation": "all three channels derive from ONE Reading stream: envelope_suspect, cons_alarm, cons_judgeable, cons_r_max and cons_switch are separate fields of ml.serve.Reading",
            "fsm_instances_are_independent": "the two FSM channels MUST be two separate DetectorFSM instances. Sharing one instance mixes self._cs, self._ca and self._quiet between channels and corrupts both in a way that is hard to see. A test asserts this before the R-set is opened.",
            "conservation_mode_for_the_pass": "shadow",
        },

        "combined_channel_suppression": {
            "fact": "Reading.violating holds envelope columns only; cons_switch is never added. A residual-only alarm has local == {} and is NEVER suppressed by ml/fsm.py",
            "not_repaired": "giving the residual a locality is a new mechanism = a second variant",
            "claims": "S7 and S11 are claimed for envelope_only only; combined on R-O3/R-C is descriptive",
            "prediction": "combined may enter suspect on R-O3 when the admin_down detour accumulates a queue and raises a residual-only alarm; because that alarm has no locality, InterventionLog cannot suppress it. This is descriptive and is not used for S7/S11 claims.",
        },

        "single_pass_requirement": {
            "rule": "ONE scan of the snapshots produces all three channels",
            "why": "F6 (amendment 1) needs S2 of the COMBINED channel; the SLO table needs S2 of envelope_only; P1/P2/F5 need the residual channel. Measuring them separately would open R-S three times.",
            "mechanical_guard": "read_snapshots_once() raises on a second read of the same path; the receipt records n_files_read",
        },

        # ------------------------------------- properties, not choices (D2)
        "observed_properties": {
            "note": "These are NOT analysis choices. They are behaviours of frozen, pinned code. Registering them as choices would manufacture researcher degrees of freedom that could be spent after seeing the data.",
            "false_alarm_event": {
                "definition": "a Transition with changed == True whose state enters the alarm zone from a state outside it",
                "alarm_zone_for_S2_S3": "{suspect, act}",
                "source": "ml/fsm.py",
                "fsm_sha256": C.sha256_file(C.ROOT / "ml/fsm.py"),
                "unknown_breaks_an_event": True,
                "why": "ml/fsm.py calls self._reset() on the unknown branch, and base = 'normal' if self.state in ('warming_up','unknown'). So an unknown tick clears self._quiet before hysteresis can count and returns the state to normal on the next tick. release_m plays no part across an unknown tick.",
                "truth_table_measured_on_frozen_fsm": [
                    {"sequence": "n a a u n a a",
                     "states": "normal suspect suspect unknown normal suspect suspect",
                     "events": 2,
                     "shows": "unknown breaks the event; release_m is bypassed"},
                    {"sequence": "n a a n a a",
                     "states": "normal suspect suspect suspect suspect suspect",
                     "events": 1,
                     "shows": "a quiet gap shorter than release_m is collapsed by hysteresis"},
                    {"sequence": "n a a n n n a a",
                     "states": "normal suspect suspect suspect suspect normal suspect suspect",
                     "events": 2,
                     "shows": "a quiet gap of release_m ticks ends the event"},
                ],
                "changing_this_means": "changing ml/fsm.py, which changes the frozen configuration and breaks the freeze tag",
                "sensitivity_analysis": "also report the count under 'consecutive raw alarm ticks', one line, so a reader can see the number does not hinge on collapsing. Phase 6 measured_baseline used that rule (F-flood-h1_to_srv1 ticks 41..47 counted as 1 event).",
            },
        },

        # ------------------------------------------------ operational definitions
        "operational_definitions": {
            "alarm_level_for_S2_S3": "suspect_level",
            "alarm_level_reported_as_second_column": "act_level",
            "alarm_level_for_G2": "act_level (amendment 3, unchanged)",
            "why_suspect_level": "PRIMARY REASON, precedent: phase6_anchors already reports excess_eval_primary{recall, fpr_all} and dual_eval_primary{recall, fpr_all, precision}, a complete sensitivity+specificity pair per channel, never recall from one channel with FPR from another. Phase 6 respected operating-point symmetry and 6R.7 only has to avoid breaking it. SECONDARY REASON, symmetry: S1 sli is 'per_incident_detection_rate (tang suspect)', so reporting S1 at the loose level and S2 at the strict level would combine the highest achievable sensitivity with the lowest achievable false-alarm rate, from two different operating points.",
            "why_not_the_provenance_argument": "the S2 target 3.0/hour derives from 0 false alarms in 278 steady ticks. Zero is zero at either level, so the target's provenance does NOT pin the level. Recorded so this prereg does not claim a stronger reason than the evidence supports.",

            "evidence_sets": {
                "note": "three NESTED physical-evidence sets. Nesting is what makes the reported columns monotone, so no choice between the SLO and amendment 4 has to be made.",
                "E_strict": ["lossPct > 1.0", "qdiscDropDelta > 0", "state_up == 0"],
                "E_sensitive": ["lossPct > 0", "qdiscDropDelta > 0", "state_up == 0"],
                "E_residual": ["lossPct > 0", "qdiscDropDelta > 0", "state_up == 0", "residual r_max > R"],
                "nesting": "lossPct > 1.0 implies lossPct > 0, so E_strict subset E_sensitive subset E_residual",
                "consequence": "FP(E_strict) >= FP(E_sensitive) >= FP(E_residual), monotone by construction",
                "conflict_resolution": "the SLO S10 fp_thuc uses lossPct > 0 with no residual; amendment 4 physically_justified_tick raises loss to 1.0 AND adds residual. Those two edits move in OPPOSITE directions, so a single 'amendment 4 column' would have an undetermined sign. Nesting removes the need to choose.",
                "selection_principle": "at each point of use, take the direction that PENALISES the detector, and say that it was chosen that way. A single definition used everywhere is the wrong target, because the self-penalising direction is opposite for S4 and for S10.",
            },

            "missing_evidence_rule": {
                "rule": "lossPct is None (qdiscValid == False) is NOT evidence, and is NOT 'checked and no evidence' either. Such ticks are counted separately as n_ticks_evidence_undetermined.",
                "why": "None means NOT MEASURABLE, not ABSENT. Folding it into 'no evidence' would inflate the false-positive columns and hide a measurement problem. This is the judgeable71 lesson applied to a new place.",
                "implementation": "explicit comparison: isinstance(value, (int, float)) and value > threshold",
                "phase5_census": {"n_link_ticks": 7665, "lossPct_is_None": 136,
                                  "source": "F-* and N-* runs, 960 ticks"},
            },

            "rho_and_the_residual_mechanism": {
                "registered_before_opening": True,
                "evidence_source": "Phase 5 raw (open since Phase 6) and sensor probe round 2 (docs/phase-6r/01e plan at f54d850, 01f results at 9dd13b8). The R-set is not touched.",

                "claim": "The conservation residual measures the RATE OF QUEUE ACCUMULATION at a switch, diluted by that switch's unrelated traffic. It does not measure packet loss and it does not require the queue to overflow. With the dilution measured on Phase 5, the model predicts which R-D cells the residual detects, and it predicts that F1 stays silent by exactly one run.",

                "measurement": {
                    "method": "per tick in (inject, revert]: switch inflow and outflow summed from ml.conservation.incidence over flatten_snapshot; imbalance = inflow - outflow; backlog = cumulative imbalance; r from ml.conservation.residuals",
                    "F-degrade-s1-s2-s3003-r1": {
                        "switch": "s1", "link": "s1-s2",
                        "host_tx_sum_mbps_first_last": [6.50, 6.42],
                        "switch_inflow_median_mbps": 6.557,
                        "imbalance_median_mbps": 0.921,
                        "backlog_cum_end_mb": 2.286,
                        "offered_on_link_pre_mbps": 4.281, "capacity_mbps": 3.451,
                        "dilution_d": 0.653,
                        "r_predicted_undiluted": 0.194, "r_predicted_diluted": 0.127,
                        "r_measured_median": 0.141,
                        "n_ticks_with_qdisc_drop": 0,
                    },
                    "F-degrade-s2-s3-s3004-r1": {
                        "switch": "s2", "link": "s2-s3",
                        "host_tx_sum_mbps_first_last": [6.46, 6.45],
                        "switch_inflow_median_mbps": 6.551,
                        "imbalance_median_mbps": 1.159,
                        "backlog_cum_end_mb": 2.744,
                        "offered_on_link_pre_mbps": 2.156, "capacity_mbps": 1.0,
                        "capacity_note": "the sealed factor asks for 0.899 Mbps; rl/scenarios.py clamps new_bw at max(1.0, ...), the documented defect in amendment 1 r_d_design_correction",
                        "dilution_d": 0.329,
                        "r_predicted_undiluted": 0.536, "r_predicted_diluted": 0.176,
                        "r_measured_median": 0.176,
                        "n_ticks_with_qdisc_drop": 9, "total_drops": 815, "first_drop_tick": 31,
                    },
                },

                "mechanism": {
                    "conservation_law": "inflow = outflow + d(backlog)/dt + dropped, so r(S) = (inflow - outflow) / inflow = [d(backlog)/dt + dropped] / inflow. The residual sees accumulation AND loss; the drop counter sees only loss.",
                    "senders_do_not_slow_down": "host transmit rates stay flat through the fault (6.50 -> 6.42 and 6.46 -> 6.45 Mbps). The client flows use loss-based congestion control and the s2-s3 background flow is UDP (mininet/traffic.py starts it with iperf -u), so nothing reduces its sending rate until packets are lost. The excess goes into the netem queue.",
                    "why_loss_lags": "the queue fills at (offered - capacity) and only drops once it holds its limit. Overflow time = queue bytes / excess rate. Loss is a LAGGING indicator; accumulation is immediate. That is the mechanical reason the residual catches what a loss-based witness misses.",
                    "why_the_links_differ": "netem limit counts PACKETS. s2-s3 carries UDP (~1.48 kB per skb, probe v2 C0), s1-s2 carries TCP with GSO on (~2.85 kB per skb, probe v2 C1), so the queue holds about twice as many bytes on s1-s2. The links are not comparable on 'did it overflow' but are comparable on accumulation rate.",
                    "why_the_envelope_misses_it": "the envelope models per-channel LEVELS. The degraded link's txRate is capped at its new capacity by the shaper, and 3.38 Mbps on s1-s2 is a level the envelope saw at lighter calibration loads, so max_k = 0. The residual models a RELATIONSHIP between channels, inflow against outflow at a switch, and the accumulation is exactly a broken relationship. The 'model the demand-capacity relationship instead of absolute levels' direction proposed for FM1 is what the residual already does.",
                },

                "earlier_mechanism_statements_withdrawn": {
                    "withdrawn_1": "'TCP is a closed loop; the sender slows down until the offered load matches the new capacity; TCP absorbs the fault losslessly.' Refuted by the flat host transmit rates. Nothing slowed; the queue absorbed the excess.",
                    "withdrawn_2": "'rho_during collapses to 1.0 because a closed loop equilibrates at capacity.' rho_during is measured on the degraded link itself, whose output the shaper caps at capacity. It sits near 1.0 for TCP and UDP alike, and the s2-s3 background flow is UDP, which cannot equilibrate by backing off. rho_during is a shaper ceiling, not a dose, and not a congestion-control equilibrium.",
                    "withdrawn_3": "'residual is mechanically a packet-loss meter; R = 0.0797 is a 7.97% loss threshold.' Refuted: 16/20 alarms with zero drops on every link.",
                    "withdrawn_4": "'the mechanism is NOT ESTABLISHED.' Too modest; see mechanism_status_by_condition.",
                    "withdrawn_5": "'the saturation threshold lies in required reduction (19.4%, 53.6%) and sets detection.' Required reduction sets OVERFLOW TIME, not detection. Detection is set by diluted accumulation against R.",
                    "withdrawn_6": "'F1 will fire, 4/6, hinging on the rho125 runs' (a draft by the reviewer) and 'F1 does not fire because the Phase 5 replicate was detected' (an earlier draft of mine). The first assumed detection needs overflow; the second reached the right count for an incomplete reason and did not see that s2-s3 rho125 is predicted undetected.",
                    "why_kept": "all six are recorded rather than deleted. A prereg that did not change before opening was not checked against data that was already available.",
                },

                "mechanism_status_by_condition": {
                    "s2-s3, offload on (probe v2 C0 and Phase 5 s3004)": "ESTABLISHED, class QUEUE_THEN_DROP. Mass balance closes (1.0031, 1.0035); drops begin when the queue holds its limit; the diluted accumulation model predicts r to three decimals (0.176 vs 0.176).",
                    "s1-s2, offload off (probe v2 C2)": "ESTABLISHED. Mass balance closes (1.0063, 1.0459).",
                    "s1-s2, offload on (probe v2 C1, the R-campaign condition)": "NOT ESTABLISHED BY THE SEALED RULE. Closure 0.9221 and 0.9108, first-drop qlen 980 and 970 against a registered 995, so conclude() withheld SENSOR_CORRECT_ON_S1S2. That verdict is NOT upgraded here: upgrading it now would re-score probe round 2 after seeing its data, which 01f itself forbids. What Phase 5 adds on this condition is weaker and is stated as such: flat host rates, 0.921 Mbps of imbalance, 2.286 MB accumulated without overflow, and r predicted 0.127 against 0.141 measured (11% high).",
                    "C1_two_anomalies_are_one": {
                        "observed": ["closure 0.9221 / 0.9108: about 8% of missing bytes unexplained by backlog + dropped",
                                     "first-drop qlen 980 / 970: drops begin before the 1000-packet limit"],
                        "single_hypothesis": "with offload on, netem's limit counts PACKETS while the balance is kept in BYTES; a GSO super-packet counts once in qlen but carries several segments, so the two ledgers diverge",
                        "status": "HYPOTHESIS, untested. C1 is not upgraded.",
                        "affects": "5/10 R-D runs (link s1-s2) and F-degrade-s1-s2-s3003-r1",
                        "for_phase7": "probe round 3 for C1 only: record the qdisc backlog in bytes (tc -s qdisc) alongside qlen in packets",
                    },
                    "C1_and_the_s1s2_misfit_cannot_both_be_innocent": {
                        "fact": "the dilution model misfits s1-s2 by +10.9% in the rate-based imbalance (predicted excess 0.8305 Mbps, measured in-out 0.9212) and fits s2-s3 to +0.2% (1.1559 vs 1.1585). The misfit is in inflow - outflow computed from byte rates, which is exactly the quantity the residual uses.",
                        "H_qdisc": "the C1 hole lives in netem's packet and backlog reporting under GSO. Then the byte-rate residual is untouched by it, and the s1-s2 misfit needs a separate explanation.",
                        "H_counter": "the C1 hole lives in the byte-rate counters under GSO. Then the s1-s2 misfit IS its trace, and the residual on s1-s2 with offload on carries a bias of about +11%.",
                        "why_both_are_registered": "a reviewer suggestion stated both that the C1 hole does not affect the rate-based residual AND that the s1-s2 misfit may be a trace of the C1 hole. Those two statements are mutually exclusive, so neither is registered as fact; the pair is registered as competing hypotheses.",
                        "direction_if_H_counter": "a +11% bias raises r on s1-s2, making those three cells EASIER to detect. It cannot rescue a miss there that would otherwise be predicted, and none is.",
                        "the_diagnostic_cell_is_insulated": "the one non-trivial prediction, s2-s3 rho125, sits on s2-s3, carrying UDP (no GSO), where C0 closes (1.0031, 1.0035) and the model fits to 0.1%. The verdict-bearing cell does not depend on how C1 resolves.",
                    },
                    "consequence": "five of the ten R-D runs are on s1-s2 with offload on. Predictions for those cells rest on the accumulation model with an 11% fit error and an unclosed mass balance, and are labelled lower-confidence than the s2-s3 cells.",
                },

                "dilution_model": {
                    "form": "r(S) ~= (offered_link - capacity) / inflow_switch = (1 - 1/rho_pre) * d, with d = offered_link / inflow_switch",
                    "fit": "s2-s3: predicted 0.176, measured 0.176. s1-s2: predicted 0.127, measured 0.141.",
                    "effective_detection_threshold": "(1 - 1/rho) * d > R  <=>  rho > 1 / (1 - R/d)",
                    "values": {"s1-s2": {"d": 0.656, "rho_eff": 1.138},
                               "s2-s3": {"d": 0.329, "rho_eff": 1.319}},
                    "the_undiluted_limit_is_not_a_result": "with d = 1, R = 0.0797 corresponds to rho > 1.0866, which lies within 1.2% of the sealed rho_detect = 1.10. That agreement is NOT registered as a convergence of two independent constants. Neither link operates at d = 1 (0.656 and 0.329), and in the operating regime the effective thresholds are 1.138 and 1.319. On s2-s3 the effective threshold is above the rho125 step. The near-match at d = 1 is a property of an idealisation the data does not support.",
                    "consequence_for_rho_detect": "rho_detect = 1.10 is roughly right for s1-s2 and too LOW for s2-s3, because s2 carries twice as much traffic unrelated to the constrained link. The cause is dilution, not TCP absorption. rho_detect stays sealed and unchanged; this is reported as a limit of the residual, not a reason to move the threshold.",
                    "a_structural_property_not_a_caveat": "r(S) normalises by the WHOLE inflow of the switch while the imbalance is produced on ONE link. One global R applied to a per-switch relative quantity therefore gives a different effective sensitivity at every switch: 1.138 on s1-s2 against 1.319 on s2-s3, a 16% difference caused only by s2 carrying h1+h3 -> srv1 traffic unrelated to the s2-s3 fault. The detector is more sensitive where the network is quiet and less sensitive where it is busy, which is the opposite of what an operator wants. This follows from the choice of denominator and is stated as a property of the formula, not as an observation on two runs.",
                    "a_real_limitation_of_the_residual": "its sensitivity to a fault on a link falls with the share of the switch's traffic that crosses that link. A core switch carrying much unrelated traffic hides a fault on one of its links. Phase 7 should report d per link as an operating property.",
                },

                "witnesses_per_run": {
                    "saturation_witness": {
                        "backlog_cum_bytes": "sum over the fault window of (inflow - outflow) at the argmax switch",
                        "backlog_rate_mbps_median": "median of (inflow - outflow)",
                        "answers": "did offered load exceed capacity",
                    },
                    "overflow_witness": {
                        "n_ticks_with_qdisc_drop": "int",
                        "total_drops": "int",
                        "overflow_time_estimate_s": "queue bytes / backlog rate, compared with the 20 s window",
                        "answers": "did the queue hold its limit within the window. NOT whether the link saturated: F-degrade-s1-s2-s3003-r1 accumulated 2.286 MB with 0 drops.",
                    },
                    "dilution_d": "offered_link / inflow_switch, so a reader can compute the expected r and compare it with the measured r",
                    "R_for_comparison": 0.0796613817054327,
                },

                "dose_ladder_predictions": {
                    "inputs": "offered from amendment 1 prior (s1-s2 4.300, s2-s3 2.157 Mbps); inflow from Phase 5 (s1 6.557, s2 6.551 Mbps); queue bytes from probe v2 (s1-s2 C1: 975 x 2852.7 B; s2-s3 C0: 1000 x 1476.6 B)",
                    "cells": [
                        {"link": "s1-s2", "rho_pre": 1.25, "capacity": 3.4400, "r_pred": 0.1312, "r_over_R": 1.65, "detect": True,  "overflow_s": 25.9, "drops_in_window": False},
                        {"link": "s1-s2", "rho_pre": 1.50, "capacity": 2.8660, "r_pred": 0.2187, "r_over_R": 2.75, "detect": True,  "overflow_s": 15.5, "drops_in_window": True},
                        {"link": "s1-s2", "rho_pre": 2.00, "capacity": 2.1500, "r_pred": 0.3279, "r_over_R": 4.12, "detect": True,  "overflow_s": 10.3, "drops_in_window": True},
                        {"link": "s2-s3", "rho_pre": 1.25, "capacity": 1.7255, "r_pred": 0.0659, "r_over_R": 0.83, "detect": False, "overflow_s": 27.4, "drops_in_window": False},
                        {"link": "s2-s3", "rho_pre": 1.50, "capacity": 1.4380, "r_pred": 0.1098, "r_over_R": 1.38, "detect": True,  "overflow_s": 16.4, "drops_in_window": True},
                        {"link": "s2-s3", "rho_pre": 2.00, "capacity": 1.0785, "r_pred": 0.1646, "r_over_R": 2.07, "detect": True,  "overflow_s": 11.0, "drops_in_window": True},
                    ],
                    "rho_le_0_9": "offered below capacity, no accumulation, r near background (Phase 5 pre-inject median 0.004), so all four are predicted silent and P2 passes",
                    "dose_ladder_floor_margin": "every corrected step stays above the 1.0 Mbps clamp; the closest is s2-s3 rho200 at 1.0785 Mbps, 7.85% headroom in bandwidth and 1.57 percentage points in the factor",
                },

                "prediction": {
                    "P_F1_silent_by_one_run": "5 of 6 runs with rho_pre >= 1.10 are detected, 83.3% against the 75% threshold, so F1 stays silent. One more miss would fire it.",
                    "P_the_one_miss": "R-D s2-s3 rho125 is predicted UNDETECTED by the residual: r_pred = 0.0659 = 0.83 R, because d on s2 is 0.329. This is a knife-edge prediction, 17% below R, and it is the prediction in this block most likely to be wrong in either direction.",
                    "P_overflow_pattern": "drops within the window on both rho150 and both rho200 runs (overflow 10-16.4 s); no drops on either rho125 run (overflow 25.9 s and 27.4 s). rho200 overflows around tick 30-31.",
                    "P_detection_and_overflow_come_apart": "s1-s2 rho125 is detected without dropping a packet; s2-s3 rho125 neither drops nor is detected. The two witnesses must be read separately.",
                    "P_rho200_saturates": "kept from the reviewer's bet and now stated as an OVERFLOW prediction: drops on both rho200 runs. If rho200 shows zero drops on both links, the queue-capacity figures from probe v2 do not transfer to R-D, and every overflow_s above is wrong.",
                },

                "discriminating_test": {
                    "mechanism_is_WRONG_if": "an R-D run shows sustained accumulation with backlog_rate / inflow > R, and the residual does not detect it. Then the quantity the residual is supposed to measure was present and it failed to see it. I accept F1 on that run with no appeal.",
                    "dilution_model_scoring": {
                        "unit_of_prediction": "the SIGN of (r_obs - R) per cell, not the value of r. The model is used to predict a decision, so it is scored on the decision.",
                        "predicted_signs": {"s1-s2_rho125": "detect", "s1-s2_rho150": "detect", "s1-s2_rho200": "detect",
                                            "s2-s3_rho125": "SILENT", "s2-s3_rho150": "detect", "s2-s3_rho200": "detect"},
                        "why_no_tolerance_on_r": "an earlier draft refuted the model only if r missed by more than 25%. The thinnest decision margin is 17% (s2-s3 rho125 at 0.83 R), so a 25% band would declare the model sound while its key cell flipped from silent to detect. A tolerance on r would have to be narrower than the thinnest margin to distinguish anything; scoring the sign removes the parameter.",
                        "why_no_aggregate_refutation_count": "a rule such as 'refuted if 2 or more signs are wrong' is itself a free threshold, and with 6 cells it would issue a verdict the data cannot carry: under a 50/50 guessing null, P(at least 5 of 6 right) = 7/64 = 0.109 and P(6 of 6) = 1/64 = 0.016. So no count cutoff is registered. Each cell's sign is reported, with those null probabilities beside the total.",
                        "the_single_diagnostic_cell": "five cells predict 'detect' and would be right under a much cruder model such as 'rho > 1.1 alarms'. Only s2-s3 rho125 separates the dilution model from the crude one. ALL of the model's discriminating power sits in that one cell. If it is detected, the dilution model's only non-trivial prediction has failed and the model is reported as seriously weakened.",
                        "a_detect_cell_that_goes_silent": "is not scored here; it is governed by mechanism_is_WRONG_if (sustained accumulation above R that the residual misses is F1 with no appeal)",
                        "descriptive_fit_no_threshold": "report |r_obs - r_pred| / r_pred per cell so the quantitative fit is visible (Phase 5: 0.1% on s2-s3, 11.1% on s1-s2), with no threshold on it",
                    },
                    "the_one_miss_is_WRONG_if": "s2-s3 rho125 is detected. That is not a failure of P1 (it would make 6/6), but it refutes the dilution threshold on s2-s3 and I report it as such.",
                    "specificity_is_WRONG_if": "F3: residual alarms on more than 2% of R-D background ticks.",
                },

                "specificity_and_where_the_risk_sits": {
                    "F3_scope": "F3 counts residual alarms on R-D BACKGROUND ticks (2M per client). amendment 1 R_N_note excludes R-N from F3.",
                    "P_F3": "F3 is predicted to PASS: at 2M per client offered stays below capacity, and Phase 5 background at this load shows r median 0.002-0.004 with 0 alarms in 4 runs of 58 ticks.",
                    "where_the_risk_actually_is": "at R-N 8-10 Mbps per client, offered on s1-s2 reaches 80-100% of capacity, so bursts can accumulate transiently and the residual can fire. That regime feeds S10 only, which is report-only. No registered gate refutes the residual on high-load false alarms.",
                    "declared_coverage_gap": "the load regime where the residual is most likely to false-alarm is covered by a report-only SLO. This is not repaired inside 6R (it would add a gate after the fact); it is declared here and carried into the model card and Phase 7.",
                    "correction_to_the_reviewer": "an earlier suggestion read 'F3 is now the main risk'. The risk is real but it does not land on F3, because F3 is scoped to R-D background at 2M per client.",
                },

                "release_scope_restriction_not_a_new_gate": {
                    "what_amendment_1_says": "all_pass -> release conservation-1.0.0 with suspect = excess OR residual",
                    "what_is_NOT_gated": "specificity above the acceptance load. Every gated R-campaign group (R-C, R-D, R-O, R-S) runs at exactly 2.0 Mbps per client (phase6r_rcampaign_matrix.json). R-N at 6/8/10 Mbps is excluded from F3 by amendment 1 R_N_note, and S10 reports without a threshold.",
                    "why_it_matters_mechanically": "the residual measures queue accumulation, so it fires on ANY transient queue, benign bursts included. At 80-100% of s1-s2 capacity (R-N 8 and 10 Mbps) queues form routinely.",
                    "action": "no new gate. If released, conservation-1.0.0 carries a declared operating envelope: 'accepted at 2 Mbps per client, the load of every gated acceptance group. Calibration covered 1-4 Mbps per client and a varying profile, but no acceptance gate was measured there. Behaviour at higher load is REPORTED in S10 and is NOT guarded by any 6R gate. Phase 7 must guard it before use above 2 Mbps per client.'",
                    "narrower_than_suggested": "a reviewer draft read 'accepted at <= 4 Mbps per client (the calibration region)'. Calibration is not acceptance: the gates saw only 2 Mbps per client, so the claim is held to 2.",
                    "why_this_is_legitimate": "narrowing the CLAIM does not change a decision rule; adding a gate after seeing the numbers would. A coverage gap found after the rules are locked is handled by saying less, not by measuring more.",
                },
                "future_work_link_level_residual": {
                    "direction": "localise to the LINK and normalise by that link: r(L) = (in_L - out_L) / max(in_L, floor). No dilution by unrelated switch traffic.",
                    "side_effect": "F4 currently scores localisation at switch level (argmax_switch). Link-level localisation would remove the dilution AND make the localisation claim stronger at once.",
                    "alternative": "an absolute byte-rate threshold alongside the relative one, taking the max; also dilution-free, but it needs per-link recalibration",
                    "not_done_now": "the configuration is frozen before the R-set is opened",
                },
                "what_does_NOT_change": [
                    "rho_detect = 1.10 and rho_silent = 0.90 (amendment 1 forbidden)",
                    "P1/P2/P3 are adjudicated on rho_pre exactly as registered",
                    "F1-F6 keep their thresholds and registered reading",
                    "amendment 1 outcomes",
                    "the probe round 2 verdict, including the withheld SENSOR_CORRECT_ON_S1S2",
                ],
                "legality": "amendment 1 forbids moving a threshold and adding a variant. Reporting explanatory covariates (backlog, d, overflow time) and registering predictions about them is neither. Every verdict is still computed exactly as sealed.",
                "why_this_is_not_post_hoc_rescuing": "every prediction above names the cell, the number and the direction before opening, and each has a stated condition under which it is wrong. The one prediction that implies a P1 miss names its run.",
            },

            "S4_clock": {
                "headline": "t_detect_from_inject",
                "definition": "from sidecar.interventions.t_start (R-campaign) or run.t_inject (Phase 5 rehearsal) to the first Transition into the alarm zone inside the incident window",
                "secondary": "t_detect_from_evidence, clocked from the first tick in the window satisfying E_sensitive",
                "why_the_inject_clock_is_the_headline": "MEASURED, not argued. On Phase 5 F-degrade-s2-s3-s3004-r1 the first E_sensitive evidence appears at tick 31 (+11.1 s, lossPct 37.121 on link-s2-s3) while the detector first alarms at tick 22 (+2.1 s). The evidence clock therefore yields -9.0 s: the detector alarms NINE SECONDS BEFORE any loss or drop evidence exists, because degrade is visible in rate and queue excess before it is visible in loss. An evidence clock built from loss is DOWNSTREAM of the detector's actual signal and is not a valid start time for the group S4 is measured on.",
                "logical_relation": "t_detect_from_inject >= t_detect_from_evidence in every case measured, so the inject clock is an UPPER BOUND on the quantity the SLO intends. Passing the upper bound implies passing the intended quantity, so this choice is self-penalising and the verdict it produces is the stronger claim.",
                "mechanism_why_loss_lags_rate": "a queue is an INTEGRATOR. Senders do not slow down (host transmit rates stay flat through the fault), so the excess (offered - capacity) accumulates in the netem queue and loss appears only once the queue holds its limit. Overflow time = queue bytes / excess. On F-degrade-s2-s3-s3004-r1 the excess was 2.156 - 1.0 = 1.16 Mbps, where 1.0 is the capacity DELIVERED after rl/scenarios.py clamps new_bw at max(1.0, ...), and the UDP queue of ~1.48 MB overflowed at tick 31. On F-degrade-s1-s2-s3003-r1 the excess of ~0.92 Mbps accumulated 2.29 MB into a TCP+GSO queue that holds ~2.78 MB, so it never overflowed within the 20 s window. One mechanism, two overflow times. See rho_and_the_residual_mechanism.",
                "why_not_a_rate_based_t_start": "a rate-deviation threshold would be the model's own threshold E, which makes the variant define its own start time. That is the same circularity as the residual clock, in a different dress.",
                "residual_excluded_from_both_clocks": True,
                "why_residual_excluded": "residual is MODEL OUTPUT, not physical evidence. If it defined t_start the envelope_only and combined channels would run different clocks, their two S4 values would not be comparable, and the variant would define the start of its own measurement.",
                "phase5_measurements_for_the_record": {
                    "F-degrade-s1-s2-s3003-r1": {"E_sensitive_first": None, "first_alarm": None,
                                                 "note": "no E_sensitive evidence and no envelope detection. NOT 'no signal': the link's txRate steps 4.281 -> 3.377 Mbps under the shaper while senders keep sending; 2.29 MB accumulates in the queue without overflowing within the window."},
                    "F-degrade-s2-s3-s3004-r1": {"E_sensitive_first_s": 11.1, "first_alarm_s": 2.1},
                    "F-admin_down-s1-s2-s3001-r1": {"E_sensitive_first_s": 1.1, "first_alarm_s": 1.1,
                                                    "note": "state_up == 0 is the firing predicate"},
                    "F-flood-h1_to_srv1-s3005-r1": {"E_sensitive_first_s": 1.1, "first_alarm_s": 1.1},
                    "F-shift-s1-s2-s3007-r1": {"E_sensitive_first_s": 2.1, "first_alarm_s": 2.1},
                    "interpretation": "the evidence clock is NOT degenerate (it ranges 1.1 s to 11.1 s and is once undefined), but on the degrade family it postdates detection, which is why it cannot be the headline",
                },
                "required_receipt_fields": [
                    "t_start_minus_t_inject_by_run",
                    "n_runs_detected_before_physical_evidence",
                    "n_ticks_in_disputed_loss_band",
                ],
                "where_those_fields_live": "inside the S4 block, not in a separate diagnostics section",
                "why_inside_S4": "they are not diagnostics. They are the load-bearing evidence that the two S4 columns measure different things; a reader who sees only one number cannot tell whether the definition did any work.",
            },

            "S4_censoring": {
                "denominator": "incidents with a detection inside the window",
                "census_required_beside_every_S4_number": [
                    "n_incidents",
                    "n_detected",
                    "n_censored_channels_left_envelope",
                    "n_censored_no_channel_left_envelope",
                ],
                "mechanical_categories_only_two": "the census splits censored incidents by ONE frozen, threshold-free quantity: max over the window of k, the number of channels outside the envelope, as computed by the frozen artifact. max_k > 0 means the evidence was inside the detector's own reach and it still did not fire: a detector failure. max_k == 0 means no channel left the envelope at any tick.",
                "why_not_three_categories": "a three-way split would need to separate 'no signal at all' from 'signal present but inside the calibrated envelope', and deciding that a raw signal EXISTS requires a new threshold on a raw step size. Registering a new threshold here would create exactly the researcher degree of freedom this prereg exists to remove. So the categories stay mechanical, and the distinction is made READABLE instead of adjudicated: a per-incident evidence table carries the raw numbers and the reader classifies.",
                "per_censored_incident_evidence_table": [
                    "median_tx_pre_mbps (ticks 2..20)",
                    "median_tx_during_mbps (inject+1..revert)",
                    "step_pct",
                    "n_ticks_with_qdisc_drop",
                    "max_k",
                    "max_excess",
                    "rho_pre",
                    "rho_during",
                ],
                "why_the_table_settles_it": "for the one Phase 6 censored incident the table reads: 4.281 -> 3.377 Mbps, a 21.1% step held for 20 ticks, 0 drop ticks, max_k = 0, max_excess = 0.0. A reader can see at once that a signal was present and that not one of the 71 channels left the envelope. No threshold had to be registered to show that.",
                "phase5_precedent_restated": "F-degrade-s1-s2-s3003-r1 is exactly the one censored incident of phase6_anchors (n_detected 7/8, delay_per_run_ticks null). It is NOT an unobservable incident. The raw telemetry carries a clean 21.1% step in txRate on link-s1-s2, stable across the whole window. What is absent is DISTINGUISHABILITY BY LEVEL: the shaper caps the degraded link's output at 3.38 Mbps while the senders keep sending, and 3.38 Mbps is a level the envelope saw at lighter calibration loads, so no channel leaves the envelope (max_k = 0). The broken RELATIONSHIP between a switch's inflow and outflow is visible, and the conservation residual sees it (16/20 ticks).",
                "not_observable_versus_not_distinguishable": "'not observable' would mean there is no signal. 'not distinguishable' means the signal exists but coincides with the normal region. Only the second is true here, and the difference matters: the first is a limit of physics, the second is a limit of THIS envelope design, and only the second points anywhere.",
                "checked_for_a_free_observable": "qdiscCounters.signature is unchanged across the fault ([['netem','10:','5:1']] at ticks 15, 30 and 45), because degrade edits the parent class rate while the signature records the leaf qdisc kind. There is no free observable that was collected but unused.",
                "S1_denominator_is_NOT_changed": "S1 keeps ALL incidents in its denominator, as sealed. PRIMARY REASON: the incident IS observable, and the envelope misses it because of how the envelope is designed, so removing it from the denominator would remove a REAL LIMIT OF THE MODEL from the measurement of the model. SECONDARY REASON: excluding it would raise recall from 7/8 to 7/7, the self-favouring direction. Had the incident genuinely carried no signal, exclusion would at least have been arguable; because it carries a signal the envelope cannot separate, exclusion is wrong and not merely flattering.",
                "why_S4_may_exclude_what_S1_may_not": "S4 excludes undetected incidents because there is NO CLOCK to stop, a mechanical reason independent of the result. S1 keeps every incident because there IS a denominator: every incident is a chance to detect, including a chance the model design cannot take. The asymmetry is declared, not harmonised.",
                "estimator": "report p95_ms (the field name the sealed SLO uses), p95_equals_max, max_ms, raw_values_ms and the census",
                "p95_equals_max_proof": "the nearest-rank percentile used in 6R.6 is index = min(n-1, max(0, round(q*(n-1)))). p95 == max whenever round(0.95*(n-1)) == n-1, i.e. 0.05*(n-1) <= 0.5, i.e. n <= 11. R-D has 10 incidents and fewer after censoring, so p95 == max with certainty.",
                "raw_is_the_distribution": "with n <= 10 the raw list IS the distribution; it is not summarised",
                "forbidden": "reporting any S4 number without the census in the same place",
            },

            "S10_columns": [
                {"id": "col_a", "evidence": "E_strict", "role": "headline, most self-penalising"},
                {"id": "col_b", "evidence": "E_sensitive", "role": "the SLO definition"},
                {"id": "col_c", "evidence": "E_residual", "role": "least self-penalising, CONFIGURATION DEPENDENT"},
            ],
            "S10_reporting": "report all three; they are monotone, so 'true FP' is bracketed by [col_c, col_a]",
            "S10_col_c_caveat": "col_c uses residual > R, so under the envelope_only channel it is a COUNTERFACTUAL ('residual would have justified this tick had it been present'). Label it as such; it is not a measurement of the envelope configuration.",
            "S10_has_no_pass_fail": "target kind is 'bao, khong dat muc tieu', so there is no gaming risk in reporting three columns",

            "incident_detected_for_S1": "at least one Transition into {suspect, act} within [inject_tick + 1, revert_tick]",
            "run_detected_50pct_for_P1_P2": "amendment 1: fraction of ticks with y == 1 and eval_primary carrying a RESIDUAL alarm >= 0.50 (unchanged)",
            "cross_use_forbidden": "the two definitions measure different things (did we catch the incident at all, versus is the saturation mechanism right). Every table states which one it uses. Using one in place of the other is forbidden.",

            "S7_version": "s7_v2 (ml.oscillation.s7_v2, amendment 3)",
            "S7_v1_also_reported": True,
            "S7_v2_loosening_disclosure": "v2 is looser than v1 in exactly one place: monotone de-escalation with an act->suspect step. Registered at amendment 3, before the R-campaign was collected.",

            "S2_estimator": "one-sided 95% Poisson upper bound: lambda_u solves P(X<=k; lambda_u) = 0.05 (ml.acceptance_stats.poisson_upper_one_sided); k = 0 gives 2.996. rate_upper = lambda_u / T",
            "S2_exposure": "T = at-risk ticks x 1 s: ticks with Reading.status == 'scored' whose FSM state BEFORE the step is outside {suspect, act}; counted per channel, never the nominal 3 h (RS runs hold 3598 snapshots each)",
            "S3_relation": "the same measurement as S2 in different units. NOT a second piece of evidence. This sentence must appear beside S3 in every table.",
        },

        # ------------------------------------------------------ scope reductions
        "scope_reductions": {
            "S4": "measured on R-D. R-O1/R-O2 cannot contribute: the amendment 6 firewall publishes booleans only, and S4 needs times. R-O3 is suppressed BY DESIGN, so time_to_detect is meaningless there.",
            "S7": "measured on R-D + R-O3 + R-C (reported separately). R-O1/R-O2 cannot contribute because S7 needs state sequences.",
            "tradeoff_declared": "the amendment 6 firewall trades evidence coverage of S4/S7 for the integrity of S2/S3. The trade was chosen at amendment 6, before any result was known.",
            "not_a_silent_drop": "this section exists so nobody quietly removes 'R-O' from the measured_on cell and hopes it is not noticed",
        },

        # --------------------------------------------------- analysis commitments
        "analysis_commitments": {
            "dose_axis_1": {
                "axis": "max_separation as measured (ml.campaign.signal_check)",
                "response": "incident_detected (the S1 definition)",
                "channels": ["envelope_only", "combined"],
                "model": "logistic(detected ~ log10(separation))",
                "ci": "cluster bootstrap, UNIT OF RESAMPLING = RUN, B = 2000, seed = 20260918",
                "separation_floor": "separation < 1e-3 (signal_check rounding) is floored to 1e-3 and counted as n_floored",
                "fallback_algorithm": "monotone: ED50 = sqrt(max_miss * min_hit) (midpoint on log10); non-monotone: report overlap [min_hit, max_miss] and n_inversions, NO ED50 (ml.acceptance_stats.dose_bracket)",
                "nonconverged_cases": "one class in resample, p at 0/1, |beta| > 1e3, slope <= 0, ED50 more than 1 decade outside the data",
                "why_cluster": "the response is ONE binary value per run, so the run is the only unit; the tick-dependence argument applies to P1/P2, not to this axis",
                "nonconvergence_rule": "if more than 50% of bootstrap samples fail to converge (complete separation), DROP the logistic fit and report linear interpolation between adjacent dose steps plus a range; record n_converged and n_boot. Do not fit 5 parameters to 10 points.",
                "anchor": "the rho125 step (factor 0.828) coincides with the Phase 5 run that already FAILED (factor 0.82747), giving an external check point",
            },
            "dose_axis_2": {
                "axis": "rho = median(link txRate, ticks 2..20) / (max(1, baseline*(1-factor))*1e6/8)",
                "checks": ["P1", "P2", "P3"],
                "no_prediction_band": [0.9, 1.1],
                "refutation": ["F1", "F2", "F3", "F4", "F5", "F6"],
                "channel": "residual_only (tick level)",
            },
            "both_axes_reported": True,
            "cherry_picking_forbidden": "both axes are registered. If they disagree, BOTH are reported and the disagreement is analysed. Choosing the prettier axis is HARKing even when both were registered.",
            "decision_rule": "phase6r_amendment_1.outcomes, unchanged",
            "release_gates": "phase6r_amendment_3.phase8_release_gates G1-G4, rule: any missing gate means the FSM is not released",
            "G2_dual_radius": "report G2 under radius() and under radius_with_detour(); R-C is the calibration set so it may be measured twice",
        },

        # ------------------------------------------------------- process controls
        "no_numeric_stdout": {
            "rule": "during the acceptance pass stdout may carry only '[i/n] <run_id> ok|fail'; any other line aborts the script",
            "stderr_rule": "stderr is swallowed during acceptance; traceback details are reproduced only on Phase 5 or fixtures",
            "why": "the amendment 6 firewall logic applied to the acceptance script itself. A crash at run 23 of 25 after printing per-run numbers means 22 runs were already seen, and the second invocation is no longer a first opening.",
        },
        "results_skeleton_committed_first": {
            "rule": "phase6r_acceptance.json is committed BEFORE opening, with the full structure and every value null",
            "why": "after opening, values are filled into existing cells. No row can be added ('I also computed this') and none removed ('that one was not very meaningful'). The shape of the answer is fixed before the answer is known.",
            "test": "recursive key-path set of skeleton == that of filled, and every skeleton leaf is null; per-run data is a dict keyed by run_id from the matrix, never a list",
        },
        "read_once_guard": {
            "rule": "SnapshotReader.read_once(run_id, path) marks the resolved path seen before reading, rejects a second read, rejects Git LFS pointers, and verifies the manifest SHA-256 before parsing",
            "receipt_field": "n_files_read",
        },
        "invocation_log": {
            "file": "results/report/phase6r_acceptance_runs.log",
            "rule": "append-only and committed; write, flush and fsync BEFORE the first R-set byte; the receipt reads it back to fill n_acceptance_invocations",
            "why": "counting invocations by mechanism rather than by promise. If it is 3, report 3 and say where the first two crashed.",
            "tag_guard": "acceptance HEAD must be the commit carrying phase-6r-opened; after that tag only this log and results/report/phase6r_acceptance.json may differ",
        },
        "prereg_mutability": {
            "before_tag_phase-6r-opened": "freely amendable, one commit per change, reason in the commit message. The rehearsal runs on Phase 5/6, so anything it finds is independent of the R-set.",
            "after_tag_phase-6r-opened": "IMMUTABLE. Changing a definition after opening is changing the instrument after taking the reading.",
            "audit": "every commit touching this file must predate the tag phase-6r-opened; a test asserts it",
        },
        "rehearsal": {
            "required_before_opening": True,
            "script": "scripts/rehearse_acceptance.py",
            "data": "Phase 5 raw (train + test, open since Phase 6)",
            "imports_the_real_functions": True,
            "mechanical_guard": "assert 'data/phase6r' does not appear in the rehearsal source",
            "environment_gate": "if python/numpy/pandas differ from phase6r_equivalence.json, the rehearsal reruns the 1062/1062 equivalence in the current environment before opening",
            "stderr_policy": "stderr is swallowed during acceptance (ml.acceptance_guard.quiet_run); a failed run is debugged by reproduction on Phase 5 or fixtures",
            "why": "the acceptance pipeline is the most complex script of Phase 6R. A first crash on the R-set means the data was already seen.",
        },

        # ------------------------------------------------------------ predictions
        "predictions": {
            "P_S2": "0 events over 3 hours gives a 95% upper bound of 1.0/hour, meeting the 3.0 target",
            "P_S4": "p95 <= 3000 ms on detected incidents under the inject clock; Phase 5 detections sit at 1.1-2.1 s. n_censored > 0 because P2 predicts the rho <= 0.9 runs are not detected.",
            "P_S4_unobservable": "at least one R-D incident has NO physical evidence in its window, as F-degrade-s1-s2-s3003-r1 did in Phase 5; the low-rho steps are the candidates",
            "P_S7": "0 oscillation patterns; F-6R4-1 may still produce out-of-zone alarms after revert on R-C",
            "P_S10": "fold 0 gives k = 0 on every row, so vary already covered 4 Mbps. At 10 Mbps (100% of the s1-s2 capacity) alarms may have a genuine physical basis, so col_b < col_a clearly.",
            "P_ED50": "WIDE CI (n = 10 runs, 5 steps x 2 links); may not converge at all",
            "P_F2": "the rho = 0.5 and rho = 0.8 runs are NOT detected -- THE MOST REFUTABLE PREDICTION IN PHASE 6R",
            "P_G4": "cannot be closed inside 6R (S12 belongs to Phase 7), so the FSM is NOT released for Phase 8",
            "P_D3_threshold_impact": "the band 0 < lossPct <= 1.0 holds 15 of 7665 Phase 5 link-ticks, ALL of them in flood/shift, 0 in degrade and 0 in normal. Prediction: the >0 versus >1.0 threshold changes NEITHER S4 (R-D is degrade) NOR S10 (R-N is normal), and is expected to matter for G2 (R-C is flood/shift). The receipt reports n_ticks_in_disputed_loss_band so a reader can see whether the threshold did any work.",
        },

        # -------------------------------------------------------- failure protocol
        "failure_protocol": {
            "if_slo_fails": "RECORD THE FAIL. Analyse the mechanism. Do not change a parameter and do not rescore the R-set.",
            "repair_paths": {
                "fixable_on_train_cv": "repair it, record the history, do not touch the R-set again inside 6R",
                "needs_new_data": "an R2-set in a later phase, declared as a SECOND OPENING",
                "deterministic_proposition_only": "only S8/S9/S11 (R-O repeatable = true) may be remeasured after a mechanism repair, with thresholds unchanged; amendment 7 is the precedent",
            },
            "not_allowed": [
                "loosening an SLO threshold",
                "changing rules F1-F6",
                "changing amendment 1 outcomes",
                "adding a second variant",
                "collecting more R-set runs",
                "changing anything under operational_definitions or observed_properties after opening",
            ],
            "n_acceptance_runs_disclosed": "the receipt records how many times the script ran, read back from the invocation log",
        },

        "out_of_scope_future_work": {
            "expected_state_baseline": "the current design answers a controller action by SUPPRESSING the whole zone for the interval. On this topology the causal zone is 14 of 16 entities, so correct causal widening is nearly indistinguishable from suppressing everything. A twin knows the EXPECTED configuration, so a better design treats state_up == 0 on an administratively downed link as NORMAL while still judging lossPct on the detour corridor: no blindness and no positive feedback. Phase 7 should measure |zone| / |topology| as an operational metric.",
            "not_done_now": "the configuration must be frozen before the R-set is opened; recorded so it is clear this was considered and deliberately not done",
            "post_revert_mechanism": "the mechanism of the post-revert window of F-6R4-1 is still untested",
        },

        "timing_and_knowledge": {
            "labels_opened": False,
            "r_set_acceptance_opened": False,
            "r_set_outcomes_emitted": False,
            "r_set_snapshots_read_outcome_blind": [
                {"lesson": "6R.5B", "runs": ["RS x3"], "tool": "scripts/measure_tick_jitter.py", "emitted": "inter-arrival quantiles only"},
                {"lesson": "6R.6", "runs": ["RS x3"], "tool": "scripts/measure_phase6r_latency*.py", "emitted": "aggregate latency only (firewall_compliance in phase6r_latency_v2)"},
                {"lesson": "6R.6", "runs": ["RS x3"], "tool": "scripts/replay_phase6r_stability.py", "emitted": "R-O1/R-O2 booleans only (ml/replay_guard.py)"},
                {"lesson": "6R.6", "runs": ["RS x3"], "tool": "scripts/soak_phase6r_detector.py", "emitted": "RSS/resource metrics only"},
                {"lesson": "6R.6/A7", "runs": ["RO-ctl x2"], "tool": "scripts/replay_phase6r_s11_v2.py, scripts/diag_s11_suppression.py", "emitted": "S11 (R-O repeatable by design)"},
            ],
            "computed_in_memory_not_emitted": "FSM states and alarms on RS were computed inside the latency and replay harnesses and discarded; S2/S3 have never been emitted",
            "numbers_quoted_from": "Phase 5 raw and Phase 6 receipts, open since Phase 6",
        },
        "deviation_policy": "immutable after the tag phase-6r-opened",
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.atomic_json(
        OUT,
        {"content": content,
         "content_sha256": C.sha256_bytes(C.canonical_json(content).encode())},
    )
    print("[6R-ACCEPT] content_sha256 =", json.loads(OUT.read_text())["content_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
