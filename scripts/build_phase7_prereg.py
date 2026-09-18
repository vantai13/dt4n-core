#!/usr/bin/env python3
"""Niêm phong thiết kế Phase 7.1 trước khi chạy probe đầy đủ."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402
from ml import operating_range as O  # noqa: E402


OUT = C.ROOT / "results/report/phase7_prereg.json"
AMENDMENT_8 = "results/report/phase6r_amendment_8.json"
RELEASE = "models/detector-release-1.0.0.json"


def build_content() -> dict:
    train_paths = [C.ROOT / O.TRAIN_DIR / (run_id + ".jsonl") for run_id in O.TRAIN_RUN_IDS]
    calibration = O.threshold_from_train(train_paths)
    return {
        "prereg_id": "DT4N-P7-OPERATING-RANGE",
        "knowledge_state": (
            "Thiết kế, ứng viên và dự đoán lấy nguyên từ hướng dẫn Lesson 7.1. "
            "Trước lúc build, thao tác kiểm tra LFS đã vô tình in 3 dòng đầu "
            "RN-load8M-s4014-r2; không dùng chúng để đổi thiết kế hay ngưỡng."
        ),
        "protocol_deviation": {
            "occurred": True,
            "detail": (
                "Không thể tuyên bố blind prereg tuyệt đối: 3 dòng R-N 8M đã được "
                "hiển thị khi kiểm tra pointer. Probe đầy đủ vẫn chỉ chạy sau khi seal."
            ),
        },
        "already_seen": (
            "8 run train + 10 run C/F Phase 5 đã được tác giả hướng dẫn xem khi "
            "chọn đại lượng; kết quả P2 trên F Phase 5 là in-sample"
        ),
        "upstream_sha256": {
            relative: C.sha256_file(C.ROOT / relative)
            for relative in (AMENDMENT_8, RELEASE)
        },
        "train_sha256": {path.name: C.sha256_file(path) for path in train_paths},
        "quantity": {
            "id": O.QUANTITY_ID,
            "definition": (
                "min trên mọi host role=client của traffic.txRate*8/1e6; "
                "bất kỳ client nào rateValid!=True hoặc non-finite -> None"
            ),
            "why": "tải hợp lệ tăng đều nâng mọi client; flood một nguồn chỉ nâng một client",
            "code": "ml/operating_range.py::g",
        },
        "correction_to_phase7_plan": {
            "F7-4": (
                "9.68 Mbps là host-srv1.rxRate (tổng h1+h3), không phải txRate; "
                "so với 8 Mbps/client là trộn đại lượng đo với tham số cấu hình"
            ),
            "masking": (
                "guard theo tổng/max tải bật trên flood Phase 5 và có thể biến act "
                "thành unknown; vì vậy bị loại"
            ),
        },
        "guard": {
            "threshold_mbps": calibration["threshold_mbps"],
            "threshold_source": "max g trên tick judgeable của 8 run TRAIN Phase 5",
            "n_train_rows": calibration["n_rows"],
            "n_train_unjudgeable": calibration["n_unjudgeable"],
            "owner": calibration["owner"],
            "per_run_max_mbps": calibration["per_run_max_mbps"],
            "compare": "strict >",
            "enter": "1 tick g > T",
            "exit_ticks": O.EXIT_TICKS,
            "exit_source": "tái dùng fsm_params.release_m=3, không thêm tham số",
            "on_active": (
                "state công bố=unknown, cause=out_of_operating_range; evidence giữ "
                "nguyên; đặt sau fsm.step (chỗ B)"
            ),
        },
        "criteria": {
            "P1_must_fire": "mọi RN-load8M-* và RN-load10M-*: frac_guard_active >= 0.90",
            "P2_must_not_mask": "mọi RD-*, RC-* và F-* Phase 5: n_guard_active == 0",
            "report_only": "RN-load6M-*, C-*, RS-*, RO-*: báo frac, không phán quyết",
        },
        "outcomes": {
            "KN1": "P1 PASS và P2 PASS -> cài guard ở 7.3 đúng như đăng ký",
            "KN2": "P1 PASS, P2 FAIL -> không cài; ghi điều kiện triển khai",
            "KN3": "P1 FAIL -> không cài; S10 giữ REPORT_ONLY",
            "no_second_candidate": "không thử đại lượng thứ hai sau khi thấy kết quả",
        },
        "predictions": {
            "author": "giữ nguyên dự đoán được cung cấp trong hướng dẫn",
            "expected_outcome": "KN1",
            "RN-load6M": "g khoảng 6 > T nên guard bật",
            "reasoning": (
                "8 Mbps/client TCP trên link 20 Mbps dự kiến khiến mỗi client gửi "
                "trên ngưỡng train khoảng 4.31 Mbps"
            ),
        },
        "known_limitations": [
            "flood phối hợp từ mọi client giống tải đều nên guard sẽ che",
            "một client im kéo min về 0 nên guard fail-open",
            "phụ thuộc topology và giả định client có cùng profile tải",
            "T là max mẫu nên normal mới vẫn có thể vượt T",
        ],
        "data_finding": {
            "N-vary-s1008-r2": (
                "h1,h3 txRate=0 và srv1 rxRate=0 cả run nhưng checks.passed=True; "
                "không sửa tham số đã đóng băng"
            )
        },
        "data_budget": (
            "R-set chỉ được probe qua ml/operating_range.py::feasibility; "
            "hàm không nhận hay trả ngưỡng"
        ),
        "deviation_policy": "immutable after creation",
    }


def main() -> int:
    if OUT.exists():
        print("[P7.1] đã niêm phong, không ghi đè:", OUT)
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
    document = json.loads(OUT.read_text(encoding="utf-8"))
    print("[P7.1] content_sha256 =", document["content_sha256"])
    print("[P7.1] T =", content["guard"]["threshold_mbps"], "Mbps, owner =", content["guard"]["owner"])
    print("[P7.1] protocol_deviation =", content["protocol_deviation"]["occurred"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
