#!/usr/bin/env python3
"""Dong goi audit verdict Phase 8 phu thuoc vao mot tar.gz tat dinh."""
from __future__ import annotations

import glob
import gzip
import io
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import campaign as C  # noqa: E402

GLOBS = [
    "logs/phase8_ab/*/*.jsonl*",
    "logs/phase8_stability/*/*",
    "logs/phase8_soak*/*/*",
    "logs/phase8_chaos/*/*.jsonl*",
    "logs/phase8_c1_control/*/*.jsonl*",
    "logs/phase8_c3_audit.jsonl",
    "logs/phase8_confirm_audit.jsonl",
]
OUT_DIR = C.ROOT / "results/evidence/phase8"


def main() -> int:
    files = sorted(
        {
            Path(path)
            for pattern in GLOBS
            for path in glob.glob(str(C.ROOT / pattern))
            if Path(path).is_file()
        }
    )
    if not files:
        print("khong tim thay audit nao - dang chay tren clone sach?")
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = {str(path.relative_to(C.ROOT)): C.sha256_file(path) for path in files}
    raw = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for path in files:
                data = path.read_bytes()
                info = tarfile.TarInfo(str(path.relative_to(C.ROOT)))
                info.size, info.mtime, info.uid, info.gid = len(data), 0, 0, 0
                info.uname = info.gname = ""
                tar.addfile(info, io.BytesIO(data))
    blob = raw.getvalue()
    tar_path = OUT_DIR / "phase8_audits.tar.gz"
    tar_path.write_bytes(blob)
    C.atomic_json(
        OUT_DIR / "index.json",
        {
            "archive": str(tar_path.relative_to(C.ROOT)),
            "archive_sha256": C.sha256_bytes(blob),
            "n_files": len(files),
            "size_bytes": len(blob),
            "files_sha256": index,
            "extract": "tar -xzf results/evidence/phase8/phase8_audits.tar.gz  (tu goc repo)",
        },
    )
    print(
        "n_files=%d size=%.1f MB sha=%s"
        % (len(files), len(blob) / 1e6, C.sha256_bytes(blob)[:12])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
