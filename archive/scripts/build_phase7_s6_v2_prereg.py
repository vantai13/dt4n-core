#!/usr/bin/env python3
"""Dang ky TRUOC phep do lai S6 (Lesson 7.7, buoc 0). Chay va commit TRUOC soak v2.

Viet SAU khi thay S6 7.6 FAIL (2.77 MiB), TRUOC khi chay lai. Khai ca hai dieu do.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import campaign as C   # noqa: E402

OUT = C.ROOT / "results/report/phase7_s6_v2_prereg.json"
PINNED = ("results/report/phase7_soak_live.json", "results/report/phase7_soak_live_tracemalloc.json",
          "results/report/phase6r_slo.json", "bridge/detector_runner.py", "scripts/soak_phase7_live_v2.py")


def main() -> int:
    if OUT.exists():
        print("[S6v2] da niem phong:", OUT)
        return 1
    content = {
        "prereg_id": "DT4N-P7-S6-V2",
        "knowledge_state": "viet SAU khi thay S6 7.6 FAIL (2.77 MiB/30 phut), TRUOC khi chay soak v2",
        "v1_result_kept": {"file": "phase7_soak_live.json", "verdict": "FAIL", "delta_mib": 2.77},
        "cause": {
            "evidence": "tracemalloc: bridge/detector_runner.py +1725 KiB; mo phong timeline+writes "
                        "1800 tick = 1708 KiB (0.95 KiB/tick)",
            "mechanism": "bo dem NGHIEN CUU (timeline/writes, maxlen 4096) them o 7.5 chay mac dinh "
                         "trong production -> probe effect; co tran ~3.8 MiB nhung tran > nguong S6",
        },
        "repair": {
            "kind": "LOGIC (khong doi tham so SLO)",
            "what": "DetectorRunner(timeline_samples=0) mac dinh; harness do bat tuong minh 4096",
            "unit_evidence": "production +107 KiB/1500 tick (co tran), timeline +986 KiB/1500 tick",
        },
        "protocol_change": {
            "warmup_s_excluded": 300,
            "why": "7.6 series: 5 phut dau +1012 KiB, trong do timeline ~285 KiB -> ~727 KiB khoi tao "
                   "LUOI cua process TICH HOP (session HTTP, SSE, collector, sync_agent). S6 6R do "
                   "process detector-only da khoi tao xong truoc t0. Muon do cung DAI LUONG (tang = "
                   "ro ri), phai bo warmup.",
            "is_post_hoc_wrt_7_6_data": True,
            "is_pre_hoc_wrt_v2_run": True,
        },
        "unchanged": {"target": "<= 1.0 MiB", "window_min": 30, "rss_source": "/proc/self/statm[1] x PAGE"},
        "verdict_rule": "S6_v2 = delta RSS trong [warmup_end, warmup_end + 30 phut] <= 1.0 MiB",
        "also_reported_not_verdict": [
            "delta theo giao thuc v1 [0, 30 phut] tren CUNG series (de nguoi doc tu so sanh)",
            "do doc nua sau; RSS 10 phut duoi (tail) de xem co bang phang",
            "JS heap cua trang dashboard (CDP, sau GC) — Chrome +77 MiB/30 phut o 7.6",
        ],
        "predictions": {
            "S6_v2_delta_mib": "0.3-0.7 (PASS): nguon khac ~16 KiB/phut + deque so thuc co tran <=150 KiB",
            "v1_protocol_delta_mib": "0.9-1.3 (sat nguong, co the FAIL) vi gom 727 KiB warmup",
            "js_heap": "chua biet — do de phan biet cache trinh duyet voi ro ri JS",
        },
        "if_fail_again": "ghi FAIL, quy trach nhiem bang tracemalloc, KHONG doi nguong; "
                         "released giu false",
        "upstream_sha256": {rel: C.sha256_file(C.ROOT / rel) for rel in PINNED},
    }
    C.atomic_json(OUT, {"content": content,
                        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
                        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print("[S6v2] content_sha256 =", json.loads(OUT.read_text())["content_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
