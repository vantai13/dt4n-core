#!/usr/bin/env python3
"""GIA THUYET NIEM PHONG TRUOC KHI NHIN DU LIEU 8.8 (Lesson 8.8).

An so khai o phase8_gap_reconciliation.json: co che uc che toan-hoac-khong co
HAI CHE DO duoi cung mot kich thich danh nghia, va dieu kien chuyen giua chung
chua xac dinh duoc.

    chien dich 8.6:  link-s2-s3 vi pham 1846/1846 tick bao dong, uc che 0 tick
    chien dich 8.7:  link-s2-s3 vi pham    2/23 tick bao dong, uc che 554 tick

File nay ghi mot gia thuyet CO THE SAI, kem tieu chi bac bo, TRUOC khi run
Poisson 1800 s x 3 cua 8.8 ket thuc. Neu doi den khi nhin so roi moi giai
thich, do la ke chuyen chu khong phai du doan.

Chay: .venv/bin/python scripts/build_phase8_suppression_hypothesis.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_suppression_hypothesis.json"

CONTENT = {
    "hypothesis_id": "DT4N-P8.8-H-SUPPRESSION-BISTABLE",
    "lesson": "8.8",
    "sealed_before": "run Poisson 1800 s x 3 seed cua 8.8 ket thuc",
    "phenomenon": {
        "campaign_8_6_ab_arm_A": {
            "alarming_ticks": 1846,
            "with_link_s2_s3": 1846,
            "fraction": 1.0,
            "suppressed_ticks": 0,
            "gap_s": {"mean": 2.31, "min": 1.0, "max": 5.0},
        },
        "campaign_8_7_stability_flood": {
            "alarming_ticks": 23,
            "with_link_s2_s3": 2,
            "fraction": 0.087,
            "suppressed_ticks": 554,
            "gap_s": {"mean": 11.0, "min": 11.0, "max": 11.0},
        },
        "same": ["flood h1->srv1 UDP 47 Mbps", "PolicyParams giong het",
                 "detector-release-1.0.0", "cung ham tinh gap"],
    },
    "hypothesis": (
        "link-s2-s3 chi vi pham khi luong nen srv1->srv2 UDP 2 Mbps con SONG. "
        "Do la thu DUY NHAT di qua s2-s3 (mininet/traffic.py::"
        "start_server_to_server, dong 108-132: 2 Mbps tren nut co chai 5 Mbps, "
        "util ~0.4). Duoi flood 47 Mbps vao srv1, luong ra srv1->srv2 bi tranh "
        "chap tai srv1 nen toc do s2-s3 lech khoi bien da hieu chuan -> vi pham "
        "-> `local <= zone` KHONG thoa -> uc che TAT. Neu luong nen da ket thuc "
        "hoac chet, s2-s3 im, khong vi pham, va uc che BAT."),
    "mechanism_note": (
        "Luong nen chay voi `-t duration` huu han (Live truyen duration_s + 120, "
        "traffic.py cong them 5 s). Mot chien dich dai hon ngan sach do se mat "
        "luong nen GIUA CHUNG ma khong co canh bao nao - va luc do co che uc "
        "che doi che do."),
    "predictions_for_8_8_poisson": [
        "P1. Trong cac tick co `link-s2-s3` trong affected, txRate cua srv1 HOAC "
        "rxRate cua srv2 phai KHAC RO RET so voi cac tick khong co no.",
        "P2. Neu luong nen song suot run (srv2 rx ~ 2 Mbps on dinh), ty le tick "
        "bao dong chua link-s2-s3 phai CAO (> 50%) va so tick "
        "suppressed_intervention phai THAP.",
        "P3. Neu srv2 rx tut ve ~0 tai mot thoi diem, thi SAU thoi diem do ty le "
        "tick chua link-s2-s3 phai giam dot ngot va so tick suppressed phai tang.",
    ],
    "falsification": (
        "Gia thuyet BI BAC BO neu: ty le tick bao dong chua link-s2-s3 khong "
        "tuong quan voi trang thai luong nen (srv1 tx / srv2 rx), hoac neu ca "
        "hai che do xuat hien trong CUNG mot run trong khi luong nen khong doi."),
    "if_falsified": (
        "Khong bia them gia thuyet sau khi nhin so. Ghi 'bac bo' vao receipt, "
        "giu nguyen an so trong system card muc C4, va de no lai cho Phase 9."),
    "why_this_matters": (
        "Neu dung: ty le mu C12 va bao dam S11 phu thuoc mot chi tiet cua "
        "HARNESS DO chu khong phai cua he -> moi con so C12 phai khai dieu kien "
        "tai nen. Neu sai: ta co mot an so that su ve co che uc che, va do la "
        "muc so 1 cua Phase 9."),
    "measurement_change_declared": (
        "scripts/run_phase8_stability.py nay lay mau CA srv2 (truoc chi h1,h2,"
        "h3,srv1). Khong lay mau srv2 thi khong kiem duoc P2/P3. Thay doi nay "
        "duoc khai TRUOC khi run, va no khong dong cham gi den vong dieu khien."),
}


def main() -> int:
    if OUT.exists():
        print("[8.8/hypothesis] da co, khong ghi de:", OUT)
        return 1
    C.atomic_json(OUT, {
        "content": CONTENT,
        "content_sha256": C.sha256_bytes(C.canonical_json(CONTENT).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    import json
    print("[8.8/hypothesis] sha =",
          json.loads(OUT.read_text())["content_sha256"][:16], "->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
