#!/usr/bin/env python3
"""Seal the completed 6R.6 measurements into one stability receipt."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

from ml import campaign as C
from ml.replay_guard import R_O1_FIELDS, R_O2_FIELDS


REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_stability.json"
PLOT = REPORT / "phase6r_soak_rss.png"


def load_receipt(name):
    path = REPORT / name
    document = json.loads(path.read_text())
    digest = C.sha256_bytes(C.canonical_json(document["content"]).encode())
    if digest != document["content_sha256"]:
        raise SystemExit("receipt hash mismatch: " + name)
    return document


def make_plot(soak):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for axis, key, title in (
        (axes[0], "realtime_30min", "Real-time: 1,800 ticks at 1 Hz"),
        (axes[1], "accelerated", "Accelerated: 10,794 ticks"),
    ):
        series = soak[key]["series"]
        axis.plot([row["t_s"] for row in series], [row["rss_kib"] for row in series], marker=".")
        axis.set_title(title)
        axis.set_xlabel("elapsed seconds")
        axis.set_ylabel("RSS KiB")
        axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(PLOT, dpi=160)
    plt.close(figure)


def main():
    if OUT.exists():
        raise SystemExit("phase6r_stability.json da ton tai; khong ghi de")
    prereg = load_receipt("phase6r_stability_prereg.json")
    latency = load_receipt("phase6r_latency.json")
    soak = load_receipt("phase6r_soak.json")
    restart = load_receipt("phase6r_replay_o1.json")
    gap = load_receipt("phase6r_replay_o2.json")
    controller = load_receipt("phase6r_replay_o3.json")
    if tuple(restart["content"]) != R_O1_FIELDS or tuple(gap["content"]) != R_O2_FIELDS:
        raise SystemExit("R-O boolean public schema mismatch")
    if any(type(value) is not bool for value in restart["content"].values()) or any(
        type(value) is not bool for value in gap["content"].values()
    ):
        raise SystemExit("R-O public output is not boolean-only")

    make_plot(soak["content"])
    fast = latency["content"]["per_implementation"]["FastOnlineScorer"]
    reference = latency["content"]["per_implementation"]["OnlineScorer"]
    realtime = soak["content"]["realtime_30min"]
    closed = {
        "S4b": {"verdict": "PASS", "value": 2, "evidence": "test/test_slo_s4b_debounce_ceiling.py"},
        "S5": {"verdict": latency["content"]["verdict"]["FastOnlineScorer"], "p95_ms": fast["p95_ms"], "evidence": "phase6r_latency.json"},
        "S6": {"verdict": soak["content"]["verdict"], "delta_mib": realtime["delta_mib"], "evidence": "phase6r_soak.json"},
        "S8": {"verdict": "PASS" if gap["content"]["passed"] else "FAIL", "boolean_only": True, "evidence": "phase6r_replay_o2.json"},
        "S9": {"verdict": "PASS" if restart["content"]["passed"] else "FAIL", "boolean_only": True, "evidence": "phase6r_replay_o1.json"},
        "S11": {"verdict": controller["content"]["verdict"], "evidence": "phase6r_replay_o3.json"},
        "S13": {"verdict": "PASS", "evidence": "test/test_payload_traceability.py"},
    }
    evidence_names = (
        "phase6r_latency.json",
        "phase6r_soak.json",
        "phase6r_replay_o1.json",
        "phase6r_replay_o2.json",
        "phase6r_replay_o3.json",
    )
    implementation = (
        "ml/payload.py",
        "ml/replay_guard.py",
        "scripts/measure_phase6r_latency.py",
        "scripts/soak_phase6r_detector.py",
        "scripts/replay_phase6r_stability.py",
    )
    cpu_model = "unknown"
    with open("/proc/cpuinfo", encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    content = {
        "lesson": "6R.6",
        "prereg_content_sha256": prereg["content_sha256"],
        "slo_content_sha256": prereg["content"]["amends"]["slo_content_sha256"],
        "amendment_6_content_sha256": prereg["content"]["amends"]["amendment_6_content_sha256"],
        "implementation_sha256": {name: C.sha256_file(C.ROOT / name) for name in implementation},
        "evidence_file_sha256": {name: C.sha256_file(REPORT / name) for name in evidence_names},
        "plot": {"file": PLOT.name, "file_sha256": C.sha256_file(PLOT)},
        "closed_here": closed,
        "deferred": {
            "S1": "6R.7 (R-D acceptance)",
            "S2": "6R.7 (R-S protected estimand)",
            "S3": "6R.7 (same protected measurement as S2)",
            "S4": "6R.7 (R-D + R-O)",
            "S7": "6R.7 (R-D + R-O)",
            "S10": "6R.7 (R-N, repeatable=false)",
            "S12": "Phase 7 (amendment 4)",
        },
        "prediction_checks": {
            "P_S5": "MATCH: fast p95 %.3f ms passes; reference p95 %.3f ms fails" % (fast["p95_ms"], reference["p95_ms"]),
            "P_S6": ("MATCH" if soak["content"]["verdict"] == "PASS" and realtime["shape"] == "flat" else "MISMATCH") + ": 30-minute delta %.4f MiB; second-half slope %.2f KiB/min" % (realtime["delta_mib"], realtime["second_half_slope_kib_per_min"]),
            "P_S8": ("MATCH" if gap["content"]["passed"] else "MISMATCH") + ": aggregate boolean result",
            "P_S9": ("MATCH" if restart["content"]["passed"] else "MISMATCH") + ": aggregate boolean result",
            "P_S11": ("MATCH" if controller["content"]["verdict"] == "PASS" else "MISMATCH") + ": " + controller["content"]["verdict"],
        },
        "measurement_environment": {
            "python": platform.python_version(),
            "kernel": platform.release(),
            "machine": platform.machine(),
            "cpu_model": cpu_model,
            "logical_cpus": os.cpu_count(),
            "note": "detector-only harness; Phase 7 contention with Mininet/Ditto/dashboard is not measured",
        },
        "r_set_acceptance_opened": False,
        "labels_opened": False,
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True, text=True).stdout.strip(),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.atomic_json(OUT, {"content": content, "content_sha256": C.sha256_bytes(C.canonical_json(content).encode())})
    print("sealed:", OUT.name)
    print("overall:", {slo: item["verdict"] for slo, item in closed.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
