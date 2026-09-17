#!/usr/bin/env python3
"""Build envelope-1.0.0 from frozen Phase 6 artifacts without refitting."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from ml import campaign as C
from ml.detectors import envelope as E
from ml.model import EnvelopeModel, SCHEMA_VERSION


REPORT = C.ROOT / "results/report"
MODELS = C.ROOT / "models"
VERSION = "envelope-1.0.0"
OUT = MODELS / (VERSION + ".json")
RECEIPT = REPORT / "phase6r_artifact_equivalence.json"


def read_report(name: str) -> dict:
    return json.loads((REPORT / name).read_text(encoding="utf-8"))


def build_content() -> dict:
    manifest = read_report("ml_dataset_split_manifest.json")
    cv = read_report("phase6_envelope_cv.json")
    amendment = read_report("phase6_prereg_amendment_1.json")
    envelope = read_report("phase6_envelope.json")
    slo = read_report("phase6r_slo.json")

    families = E.registered_families(amendment, manifest)
    columns = families["primary"]
    if len(columns) != 71:
        raise RuntimeError("ho primary phai 71 cot, nhan %d" % len(columns))

    provenance = C.collection_provenance()
    return {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "columns": columns,
        "families": families,
        "bounds": {
            column: {
                "min": float(manifest["envelope"][column]["min"]),
                "max": float(manifest["envelope"][column]["max"]),
            }
            for column in columns
        },
        "thresholds": {
            name: {"K": int(values["K"]), "E": float(values["E"])}
            for name, values in cv["content"]["thresholds"].items()
        },
        "floors": {
            "by_suffix": dict(E.FLOORS),
            "other": float(E.OTHER_FLOOR),
        },
        "link_stats": manifest["link_stats"],
        "feature_spec": {
            "uses_delta": False,
            "delta_columns": [],
            "uses_rolling": False,
            "warmup_ticks_required": 0,
            "aggregate_fn": "ml.features.add_aggregate_features",
            "link_stats_mode": "frozen",
            "note": (
                "envelope_feature_names co 0 cot d1: scorer stateless ve feature; "
                "Phase 7 phai truyen link_stats dong bang."
            ),
        },
        "unknown_policy": (
            "any of the 71 columns non-finite -> unknown -> no alarm; "
            "never mapped to normal"
        ),
        "provenance": {
            "train_run_ids": sorted(manifest["split"]["train"]),
            "n_train_rows_envelope": int(manifest["envelope_fit_train_rows"]),
            "manifest_sha256": C.sha256_file(
                REPORT / "ml_dataset_split_manifest.json"
            ),
            "cv_content_sha256": cv["content_sha256"],
            "amendment_1_content_sha256": amendment[
                "amendment_content_sha256"
            ],
            "phase6_envelope_content_sha256": envelope["content_sha256"],
            "phase6_ticks_csv_sha256": C.sha256_file(
                REPORT / "phase6_envelope_ticks.csv"
            ),
            "slo_content_sha256": slo["content_sha256"],
            "envelope_code_sha256": C.sha256_file(
                C.ROOT / "ml/detectors/envelope.py"
            ),
            "git_hash": provenance["git_hash"],
            "built_at_utc": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        },
    }


def tier_a(model: EnvelopeModel) -> dict:
    """Verify the decision layer from the 14-column committed tick receipt."""
    import numpy as np
    import pandas as pd

    ticks = pd.read_csv(
        REPORT / "phase6_envelope_ticks.csv", float_precision="round_trip"
    )
    if len(ticks) != 590:
        raise RuntimeError("ticks CSV phai 590 dong, nhan %d" % len(ticks))
    judgeable = ticks.judgeable71.to_numpy(dtype=bool)
    judgeable_loss = ticks.judgeable_loss.to_numpy(dtype=bool)
    got = {
        "primary_k": judgeable
        & (ticks.k.to_numpy() > int(model.thresholds["primary"]["K"])),
        "secondary_excess": model.suspect_from(
            ticks.excess.to_numpy(), judgeable
        ),
        "secondary_dual": model.act_from(
            ticks.k_ind.to_numpy(), ticks.k_rate.to_numpy(), judgeable
        ),
        "ablation_loss_only": judgeable_loss
        & (ticks.k_loss.to_numpy() > int(model.thresholds["loss_only"]["K"])),
    }
    result = {}
    for name, actual in got.items():
        expected = ticks["alarm_" + name].to_numpy(dtype=bool)
        bad = np.flatnonzero(actual != expected)
        result[name] = {
            "n_rows": len(ticks),
            "n_match": int((actual == expected).sum()),
            "bit_exact": len(bad) == 0,
            "first_mismatches": [
                {"run_id": ticks.run_id.iloc[index], "tick": int(ticks.tick.iloc[index])}
                for index in bad[:10]
            ],
        }
    return result


def raw_available() -> bool:
    return len(list((C.ROOT / "data/phase5/raw").glob("*.jsonl"))) == 18


def tier_b(model: EnvelopeModel) -> dict:
    """Verify scoring values against Phase 6; requires the feature matrix."""
    if not raw_available():
        return {
            "skipped": True,
            "reason": (
                "data/phase5/raw/*.jsonl khong day du 18 file; "
                "tang cham diem khong kiem duoc"
            ),
        }
    import numpy as np
    import pandas as pd

    from ml.dataset import load_split

    split = load_split()
    ticks = pd.read_csv(
        REPORT / "phase6_envelope_ticks.csv", float_precision="round_trip"
    )
    decision = model.score_batch(split.X_test_envelope)
    return {
        "skipped": False,
        "n_rows": len(ticks),
        "k_bit_exact": bool((decision.k == ticks.k.to_numpy()).all()),
        "excess_bit_exact": bool((decision.excess == ticks.excess.to_numpy()).all()),
        "excess_max_abs_diff": float(
            np.max(np.abs(decision.excess - ticks.excess.to_numpy()))
        ),
        "judgeable_bit_exact": bool(
            (
                decision.judgeable
                == ticks.judgeable71.to_numpy(dtype=bool)
            ).all()
        ),
        "k_ind_bit_exact": bool(
            (decision.k_indicator == ticks.k_ind.to_numpy()).all()
        ),
        "k_rate_bit_exact": bool(
            (decision.k_rate == ticks.k_rate.to_numpy()).all()
        ),
        "note": "excess_max_abs_diff phai dung 0.0, khong dung epsilon",
    }


def main() -> int:
    if OUT.exists():
        print(
            "[6R.2] %s da ton tai. Artifact bat bien. "
            "Doi so -> tang version -> file moi." % OUT.name
        )
        return 1
    MODELS.mkdir(parents=True, exist_ok=True)

    model = EnvelopeModel(build_content())
    digest = model.save(OUT)
    reloaded = EnvelopeModel.load(OUT)
    if reloaded.content_sha256 != digest:
        raise RuntimeError("round-trip khong on dinh")

    decision_equivalence = tier_a(reloaded)
    scoring_equivalence = tier_b(reloaded)
    receipt_content = {
        "lesson": "6R.2",
        "artifact": {
            "path": "models/" + OUT.name,
            "version": VERSION,
            "content_sha256": digest,
            "n_columns": len(reloaded.columns),
        },
        "needs_no_data_dir": True,
        "tier_a_decision_layer": decision_equivalence,
        "tier_b_scoring_layer": scoring_equivalence,
        "tier_explanation": (
            "ticks CSV co 14 cot, khong co feature: no kiem duoc decision layer; "
            "scoring layer can ma tran 590x71 tu raw hoac fixture."
        ),
    }
    receipt = {
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content": receipt_content,
        "content_sha256": C.sha256_bytes(
            C.canonical_json(receipt_content).encode("utf-8")
        ),
    }
    C.atomic_json(RECEIPT, receipt)

    print("[6R.2] artifact   :", OUT.relative_to(C.ROOT))
    print("[6R.2] sha256     :", digest)
    print(
        "[6R.2] n_columns  :",
        len(reloaded.columns),
        "| E =",
        repr(reloaded.thresholds["primary"]["E"]),
    )
    for name, result in decision_equivalence.items():
        status = (
            "bit-exact"
            if result["bit_exact"]
            else "LECH " + str(result["first_mismatches"])
        )
        print(
            "[6R.2] tier A %-20s %d/%d %s"
            % (name, result["n_match"], result["n_rows"], status)
        )
    if scoring_equivalence["skipped"]:
        print("[6R.2] tier B     : SKIP -", scoring_equivalence["reason"])
    else:
        print(
            "[6R.2] tier B     : k=%s excess=%s judgeable=%s (max|diff|=%r)"
            % (
                scoring_equivalence["k_bit_exact"],
                scoring_equivalence["excess_bit_exact"],
                scoring_equivalence["judgeable_bit_exact"],
                scoring_equivalence["excess_max_abs_diff"],
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
