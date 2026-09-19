#!/usr/bin/env python3
"""Niêm phong amendment 1: freshness phía consumer phải đơn điệu."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase7_contract_amendment_1.json"
PINNED = (
    "results/report/phase7_contract.json",
    "bridge/freshness.py",
    "dashboard/src/lib/freshness.js",
    "test/fixtures/freshness_vectors.json",
)


def build_content() -> dict:
    return {
        "amendment_id": "DT4N-P7-CONTRACT-A1",
        "amends": "C_freshness.rules[4] (quy tac 5: 'lan dau ARM; (bootId,seq) DOI thi CONFIRM')",
        "knowledge_state": "viet khi thiet ke consumer 7.4, TRUOC khi do S12 live",
        "trigger": {
            "resync_reads_search_index": (
                "App.vue resync() -> fetchAllThings() -> /search/things "
                "(things-search: nhat quan CUOI CUNG); moi lan SSE reconnect "
                "deu resync -> co the nhan ban detector CU hon ban SSE da ap"
            ),
            "late_patch": (
                "7.3 live: 2 PATCH timeout phia client trong luc nginx pause; "
                "request da nam trong socket co the van duoc xu ly SAU ban moi hon"
            ),
            "sealed_rule_failure": (
                "(bootId,seq) DOI -> tim dap: seq LUI cung la 'doi' -> lam tuoi "
                "bang ban cu va hien thi trang thai qua khu nhu hien tai"
            ),
        },
        "new_rule": [
            "lan dau thay: ARM (chap nhan de hien thi, CHUA lam tuoi)",
            "cung bootId: chi chap nhan seq TANG CHAT; lui hoac trung -> tu choi",
            "bootId moi chua tung thay: chap nhan (restart), boot cu vao danh sach retired",
            "bootId da retired: tu choi",
            "ban tin bi tu choi: KHONG lam tuoi va KHONG duoc hien thi (bo ca ban tin)",
        ],
        "unchanged": [
            "TTL = ttlTicks*tickIntervalMs do bang dong ho consumer",
            "khong co co stale do detector dat",
            "mac dinh STALE (fail-safe)",
            "schema B khong doi",
        ],
        "superseded_for_consumers": (
            "bridge.detector_contract.FreshnessTracker -> "
            "bridge.freshness.MonotonicFreshness (Python) va "
            "dashboard/src/lib/freshness.js (JS); ban cu GIU NGUYEN, khong sua"
        ),
        "verification": "cung mot file vector cho ca Python va JS + e2e Chromium voi Ditto gia",
        "known_limitation": (
            "boot cu toi muon TRUOC khi boot moi duoc thay thi khong phan biet duoc "
            "(bootId ngau nhien, khong co thu tu); can restart < 1 tick de xay ra"
        ),
        "upstream_sha256": {
            relative: C.sha256_file(C.ROOT / relative) for relative in PINNED
        },
    }


def main() -> int:
    if OUT.exists():
        print("[P7.A1] da niem phong:", OUT)
        return 1
    content = build_content()
    C.atomic_json(OUT, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("[P7.A1] content_sha256 =", json.loads(OUT.read_text())["content_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
