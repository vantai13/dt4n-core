#!/usr/bin/env python3
"""Integrity and derivation tests for the sealed Phase 6R.1 contract."""
from __future__ import annotations

import json

import pytest

from ml import campaign as C
from scripts import build_phase6r_slo as B


DOC = C.ROOT / "results/report/phase6r_slo.json"
pytestmark = pytest.mark.skipif(not DOC.exists(), reason="Lesson 6R.1 chua chay build")


@pytest.fixture(scope="module")
def doc():
    return json.loads(DOC.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def content(doc):
    return doc["content"]


def test_content_hash_matches(doc):
    assert doc["content_sha256"] == C.sha256_bytes(
        C.canonical_json(doc["content"]).encode("utf-8")
    )


def test_written_at_not_inside_hash(doc):
    assert "written_at_utc" not in doc["content"]
    assert "written_at_utc" in doc


def test_upstream_artifacts_have_not_drifted(content):
    for rel, sha in content["upstream_sha256"].items():
        path = C.ROOT / rel
        assert path.exists(), "mat artifact upstream: " + rel
        assert C.sha256_file(path) == sha, "artifact da doi: " + rel


def test_every_slo_has_id_sli_target_and_source(content):
    ids = [item["id"] for item in content["slo"]]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 11
    for item in content["slo"]:
        assert item["sli"]
        assert item["derived_from"]
        target = item["target"]
        report_only = target.get("kind") == "bao, khong dat muc tieu"
        assert "value" in target or report_only
        if report_only:
            assert item.get("note") or item.get("report_two_columns")


def test_failure_mode_slos_present(content):
    ids = {item["id"] for item in content["slo"]}
    assert {"S8", "S9", "S11", "S12"} <= ids


def test_s8_forbids_mapping_missing_to_normal(content):
    s8 = next(item for item in content["slo"] if item["id"] == "S8")
    assert "0%" in s8["hard_constraint"] and "normal" in s8["hard_constraint"]


def test_debounce_ceiling_consistent_with_s4(content):
    s4 = next(item for item in content["slo"] if item["id"] == "S4")
    s4b = next(item for item in content["slo"] if item["id"] == "S4b")
    assert s4b["target"]["value"] == B.debounce_ceiling(s4["target"]["value"])
    assert s4b["pre_registered_choice"]["act"] <= s4b["target"]["value"]
    assert s4b["pre_registered_choice"]["suspect"] <= s4b["target"]["value"]


def test_debounce_of_three_would_breach_s4(content):
    s4 = next(item for item in content["slo"] if item["id"] == "S4")
    assert B.t_detect_p95_ms(3) > s4["target"]["value"]
    assert B.t_detect_p95_ms(2) <= s4["target"]["value"]


def test_s2_bound_matches_rule_of_three_on_declared_soak(content):
    soak_min = content["constants"]["soak_minutes"]
    s2 = next(item for item in content["slo"] if item["id"] == "S2")
    assert s2["target"]["value"] == pytest.approx(
        B.rule_of_three_per_hour(int(soak_min * 60)), rel=1e-9
    )
    assert s2["verifiable_now"] is False


def test_s3_is_declared_same_measurement_as_s2(content):
    s3 = next(item for item in content["slo"] if item["id"] == "S3")
    assert "CUNG MOT PHEP DO" in s3["note"]


def test_measured_baseline_recomputes_from_ticks_csv(content):
    assert B.measured_baseline() == content["measured_baseline"]


def test_steady_state_has_zero_false_positives(content):
    baseline = content["measured_baseline"]
    assert baseline["steady_state_fp_ticks"] == 0
    assert baseline["steady_state_normal_ticks"] == 278
    assert baseline["by_window"]["control_run_full"]["fp_excess"] == 0
    assert baseline["by_window"]["fault_run_pre_inject"]["fp_excess"] == 0
    assert baseline["by_window"]["fault_run_post_revert"]["fp_excess"] == 23


def test_all_fp_events_are_post_revert(content):
    for run, ticks in content["measured_baseline"]["fp_event_ticks"].items():
        assert min(ticks) >= 41, "%s co FP truoc revert_tick=40" % run
    assert content["measured_baseline"]["n_fp_events_total"] == 7


def test_data_budget_covers_every_6r_decision(content):
    covered = " | ".join(item["decision"] for item in content["data_budget"]).lower()
    for need in ("e, k", "link_stats", "bounds", "debounce", "cooldown", "ttl", "bien the"):
        assert need in covered
    for item in content["data_budget"]:
        assert item["allowed"]
        assert "forbidden" in item


def test_test_set_never_allowed_to_tune_a_threshold(content):
    for item in content["data_budget"]:
        allowed = item["allowed"].lower()
        if "test" in allowed:
            assert (
                "khong nhan tham so y" in allowed
                or "dem chum" in allowed
                or "khai ro" in allowed
            ), item["decision"]


def test_cooldown_final_value_comes_from_new_data(content):
    item = next(x for x in content["data_budget"] if x["decision"] == "cooldown")
    assert "R-C" in item["allowed"]
    assert "R-O" in item["forbidden"]


def test_r_campaign_rows_are_complete(content):
    groups = {item["group"]: item for item in content["r_campaign"]}
    assert {"R-S", "R-N", "R-D", "R-C", "R-O"} <= groups.keys()
    for item in content["r_campaign"]:
        assert item["n_runs"] >= 1 and item["purpose"] and item["knob"]
        assert item["role"] in ("nghiem thu", "HIEU CHINH")
        assert isinstance(item["repeatable"], bool)


def test_only_r_o_is_repeatable(content):
    for item in content["r_campaign"]:
        assert item["repeatable"] == (item["group"] == "R-O")
        if item["repeatable"]:
            assert item["repeatable_rationale"]


def test_dose_axis_is_measured_not_a_knob(content):
    rd = next(item for item in content["r_campaign"] if item["group"] == "R-D")
    assert "max_separation" in rd["dose_axis"]
    assert "DO SAU" in rd["dose_axis"]
    assert "degrade" in rd["scope"]


def test_separation_gap_is_documented(content):
    anchors = content["phase6_anchors"]
    assert anchors["separation_gap_unknown"] == [11.486, 100.0]
    assert "HANG SO CAU TRUC" in anchors["separation_ceiling_note"]


def test_slo_is_anchored_to_eval_primary_not_sensitivity(content):
    anchors = content["phase6_anchors"]
    assert anchors["mask_for_slo"] == "eval_primary"
    assert anchors["excess_eval_primary"]["recall"] == pytest.approx(0.85625)
    assert anchors["excess_eval_primary"]["fpr_control"] == 0.0
    assert "eval_sensitivity" in anchors["mask_note"]


def test_slo_sealed_before_any_6r_code_exists(content):
    assert content["sealed_before"]
    for rel in content["sealed_before"]:
        assert rel.endswith(".py")
