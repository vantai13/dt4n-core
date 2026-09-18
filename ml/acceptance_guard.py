"""Co che bao ve lan mo R-set duy nhat (6R.7); khong tinh metric tai day."""
from __future__ import annotations

import contextlib
import io
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ml import campaign as C

LFS_MAGIC = b"version https://git-lfs"
OPEN_TAG = "phase-6r-opened"
INVOCATION_LOG = "results/report/phase6r_acceptance_runs.log"
ALLOWED_AFTER_TAG = frozenset(
    {INVOCATION_LOG, "results/report/phase6r_acceptance.json"}
)


class GuardError(RuntimeError):
    """Vi pham ky luat mo R-set; loi nay khong duoc bo qua."""


class SnapshotReader:
    def __init__(self, expected_sha256: dict[str, str]):
        self._expected = dict(expected_sha256)
        self._seen: set[Path] = set()

    @property
    def n_files_read(self) -> int:
        return len(self._seen)

    def read_once(self, run_id: str, path) -> list[dict]:
        resolved = Path(path).resolve()
        if resolved in self._seen:
            raise GuardError("doc lan hai: %s" % run_id)
        if run_id not in self._expected:
            raise GuardError("run khong co trong manifest: %s" % run_id)
        self._seen.add(resolved)
        data = resolved.read_bytes()
        if data.startswith(LFS_MAGIC):
            raise GuardError("%s la con tro Git LFS; chay 'git lfs pull' truoc" % run_id)
        if C.sha256_bytes(data) != self._expected[run_id]:
            raise GuardError("SHA-256 lech manifest: %s" % run_id)
        return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=C.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _changed_paths(*diff_args: str) -> set[str]:
    return {line for line in _git("diff", "--name-only", *diff_args).splitlines() if line}


def preflight(mode: str) -> dict:
    """Kiem tra cay lam viec cho ``rehearsal`` hoac ``acceptance``."""
    if mode not in ("rehearsal", "acceptance"):
        raise ValueError(mode)
    untracked = [line for line in _git("status", "--porcelain").splitlines() if line.startswith("??")]
    dirty = _changed_paths("HEAD") | {line[3:] for line in untracked}
    head = _git("rev-parse", "HEAD")
    if mode == "rehearsal":
        if dirty:
            raise GuardError("cay lam viec ban: %s" % sorted(dirty))
    else:
        try:
            tagged = _git("rev-list", "-n", "1", OPEN_TAG)
        except subprocess.CalledProcessError as exc:
            raise GuardError("chua co tag %s" % OPEN_TAG) from exc
        drift = (_changed_paths(tagged, "HEAD") | dirty) - ALLOWED_AFTER_TAG
        if drift:
            raise GuardError("khac tag ngoai danh sach cho phep: %s" % sorted(drift))
    import numpy
    import pandas

    return {
        "mode": mode,
        "head": head,
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
    }


def log_invocation(info: dict, log_path=None) -> None:
    path = Path(log_path) if log_path else C.ROOT / INVOCATION_LOG
    entry = {
        **info,
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "argv": sys.argv,
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def count_invocations(mode: str, log_path=None) -> int:
    path = Path(log_path) if log_path else C.ROOT / INVOCATION_LOG
    if not path.exists():
        return 0
    return sum(
        json.loads(line)["mode"] == mode
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


@contextlib.contextmanager
def quiet_run():
    """Chan stderr de traceback khong lam ro ket qua niem phong."""
    sink = io.StringIO()
    with contextlib.redirect_stderr(sink):
        yield
    sink.close()


def progress(i: int, n: int, run_id: str, ok: bool) -> None:
    sys.__stdout__.write("[%d/%d] %s %s\n" % (i, n, run_id, "ok" if ok else "fail"))
    sys.__stdout__.flush()
