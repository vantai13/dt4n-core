#!/usr/bin/env python3
"""Hop dong E - audit append-only co chuoi hash (tamper-evident).

Moi dong chua SHA-256 cua dong TRUOC. Sua/xoa mot dong giua chung lam GAY
chuoi tai dung vi tri do - cung nguyen ly voi Git va so cai ngan hang.

Tamper-EVIDENT, khong phai tamper-PROOF: khong ngan duoc ai sua, nhung bao
dam viec sua bi phat hien.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

GENESIS = "0" * 64


def canonical(row: dict) -> bytes:
    """Serialize TAT DINH: sort key, khong khoang trang thua, ensure_ascii.

    Khong tat dinh -> hash khac nhau giua hai lan chay -> verify_chain bao gay
    GIA. Day la loi kinh dien khi tu lam hash chain.
    """
    return json.dumps(
        row, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def sha(row: dict) -> str:
    return hashlib.sha256(canonical(row)).hexdigest()


class AuditLog:
    """Ghi append-only, fsync moi dong, noi tiep chuoi khi restart/xoay vong."""

    def __init__(self, path, max_rows: int | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_rows = max_rows
        self._seq, self._prev = self._resume()
        self._rows_in_file = self._count_rows()

    # ------------------------------------------------------------ noi chuoi

    def _resume(self):
        """Noi tiep chuoi cu neu file da ton tai (controller restart).

        Bat dau lai tu GENESIS sau restart = chuoi gay tai dung diem restart.
        """
        if not self.path.exists():
            return 0, GENESIS
        last = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = json.loads(line)
        if last is None:
            return 0, GENESIS
        return int(last["seq"]), sha(last)

    def _count_rows(self) -> int:
        if not self.path.exists():
            return 0
        return sum(1 for line in self.path.read_text(encoding="utf-8").splitlines()
                   if line.strip())

    # ------------------------------------------------------------ ghi

    def append(self, record: dict) -> dict:
        """Ghi mot dong. fsync de crash giua chung khong mat dong cuoi."""
        if self.max_rows and self._rows_in_file >= self.max_rows:
            self._rotate()
        self._seq += 1
        row = dict(record)
        row["seq"] = self._seq
        row["prev_sha256"] = self._prev
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(canonical(row).decode("utf-8") + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._prev = sha(row)
        self._rows_in_file += 1
        return row

    def _rotate(self):
        """Xoay vong KHONG duoc lam mat dau chuoi.

        File moi ghi `rotated_from` + `rotated_head_sha256` = head cua file cu,
        va dong dau tien cua no van co prev_sha256 = head do, nen chuoi lien
        tuc QUA NHIEU FILE.
        """
        index = 1
        while True:
            target = self.path.with_name("%s.%d" % (self.path.name, index))
            if not target.exists():
                break
            index += 1
        self.path.rename(target)
        header = {
            "rotated_from": target.name,
            "rotated_head_sha256": self._prev,
        }
        self.path.write_text("", encoding="utf-8")
        self._rows_in_file = 0
        self.append(header)


def verify_chain(path, follow_rotated: bool = True) -> dict:
    """Tra vi tri GAY dau tien, hoac ok=True. Khong tu chua, chi bao cao."""
    path = Path(path)
    prev = GENESIS
    total = 0
    files = [path]
    if follow_rotated:
        files = _rotation_order(path)
    expected_seq = 0
    for file_path in files:
        for index, line in enumerate(
            file_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("prev_sha256") != prev:
                return {
                    "ok": False,
                    "file": file_path.name,
                    "broken_at_line": index,
                    "seq": row.get("seq"),
                    "expected_prev": prev,
                    "found_prev": row.get("prev_sha256"),
                }
            if row.get("seq") != expected_seq + 1:
                return {
                    "ok": False,
                    "file": file_path.name,
                    "broken_at_line": index,
                    "reason": "seq khong lien tuc",
                    "seq": row.get("seq"),
                }
            prev = sha(row)
            expected_seq = int(row["seq"])
            total += 1
    return {"ok": True, "n_rows": total, "head_sha256": prev,
            "n_files": len(files)}


def _rotation_order(path: Path) -> list[Path]:
    """Cac file da xoay vong, cu truoc moi truoc."""
    rotated = sorted(
        (p for p in path.parent.glob(path.name + ".*") if p.suffix[1:].isdigit()),
        key=lambda p: int(p.suffix[1:]),
    )
    return rotated + [path]


def read_rows(path) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
