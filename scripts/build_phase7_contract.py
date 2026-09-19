#!/usr/bin/env python3
"""Niêm phong hợp đồng live Phase 7.2 (A/B/C) trước runner 7.3."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge import collector_version as V  # noqa: E402
from bridge import detector_contract as D  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402


OUT = C.ROOT / "results/report/phase7_contract.json"
PINNED = (
    "models/detector-release-1.0.0.json",
    "results/report/phase6r_slo.json",
    "results/report/phase7_prereg.json",
    "bridge/detector_contract.py",
    "bridge/collector_version.py",
)


def build_content() -> dict:
    release = DetectorRelease.load(C.ROOT / PINNED[0])
    if V.drifted_sources():
        raise SystemExit("collector đã đổi: %s" % V.drifted_sources())
    return {
        "contract_id": "DT4N-P7-LIVE-CONTRACT",
        "upstream_sha256": {
            relative: C.sha256_file(C.ROOT / relative) for relative in PINNED
        },
        "A_snapshot": {
            "source": (
                "Collector.run RIÊNG cho detector (interval 1.0 s, net_lock chung), "
                "KHÔNG phải vòng sync_agent, KHÔNG đọc lại từ Ditto"
            ),
            "why_not_sync_agent": (
                "sync_agent PATCH đồng bộ có retry (tối đa 4 lần, timeout 5 s, "
                "backoff 1+2+4 s) nên Delta t lệch train"
            ),
            "why_not_ditto": (
                "adapter bỏ None nên Ditto giữ giá trị cũ; differ bỏ thay đổi "
                "<0.5 B/s nên không còn dữ liệu từng tick"
            ),
            "required": {
                "A1": "t_source hữu hạn",
                "A2": "tập entity == expected_entities(model) = %d entity"
                % len(D.expected_entities(release.model)),
                "A3": (
                    "run.collector_version do producer cấp từ "
                    "bridge/collector_version.py"
                ),
                "A4": "tick (có khi run_meta được truyền)",
            },
            "producer_version": V.COLLECTOR_VERSION,
            "measurement_sources_sha256": V.MEASUREMENT_SOURCES,
            "serve_py_changed": False,
        },
        "B_thing": {
            "thing_id": D.DETECTOR_THING_ID,
            "one_thing_because": "FSM trả một state/tick; Ditto ghi nguyên tử theo Thing",
            "features": {
                "decision": "state|cause|reason|detectedAt — trạng thái công bố sau guard",
                "evidence": (
                    "envelopeValid|conservationValid|envelope|conservation|actRule|"
                    "conservationSwitch|affected|unattributed — bằng chứng tick hiện tại"
                ),
                "freshness": "bootId|seq|heartbeatAt|ttlTicks|tickIntervalMs|dropped",
                "provenance": (
                    "modelVersion|artifactSha256|releaseVersion|releaseSha256|"
                    "conservationSha256|collectorVersion"
                ),
            },
            "no_null_rule": "JSON Merge Patch RFC 7396: null=xóa; body không chứa None",
            "oracle": (
                "tick không normal đối chiếu release.payload; normal dùng "
                "build_document vì payload từ chối reason rỗng"
            ),
            "guard_overrides": list(D.GUARD_OVERRIDABLE),
            "not_published": "FSM state trước guard chỉ audit local, không lên Ditto",
            "bootstrap_initial_state": "unknown/never_started, seq=-1",
        },
        "C_freshness": {
            "rules": [
                "1. PATCH freshness mỗi tick, kể cả normal",
                "2. khóa sống=(bootId,seq); không dùng timestamp",
                (
                    "3. consumer tự tính TTL=ttlTicks*tickIntervalMs=%d ms bằng "
                    "đồng hồ của mình"
                    % (D.TTL_TICKS * D.TICK_INTERVAL_MS)
                ),
                "4. detector không đặt cờ stale",
                "5. lần đầu thấy key chỉ ARM; key đổi mới CONFIRM",
            ],
            "clock_choice": "đo khoảng bằng clock consumer; không so clock hai máy",
            "worst_case_budget_ms": (
                "TTL 3000 + Ditto/SSE p95 ~1017 + consumer poll 250 = "
                "~4267 <= S12 5000"
            ),
            "consumer_action_rule": (
                "controller/UI chỉ dùng decision.state khi FRESH; "
                "không hành động theo evidence.actRule"
            ),
        },
        "deviation_policy": "immutable after commit",
    }


def main() -> int:
    if OUT.exists():
        print("[P7.2] đã niêm phong, không ghi đè:", OUT)
        return 1
    content = build_content()
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode("utf-8")),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    print(
        "[P7.2] content_sha256 =",
        json.loads(OUT.read_text(encoding="utf-8"))["content_sha256"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
