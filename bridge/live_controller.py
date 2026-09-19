"""Minimal live controller used to verify intervention ordering in Phase 7.6."""
from __future__ import annotations

import time
import uuid

from ml import campaign as C
from ml.blast_radius import Routing, radius_with_detour
from ml.intervention_log import Intervention

MODES = ("log_first", "log_late", "no_log")
SUBJECT = {"inject": "disableLink", "revert": "enableLink"}


class LiveController:
    def __init__(
        self,
        intervention_log,
        send_command,
        runner,
        routing_path=C.ROOT / "ditto/routing_table.json",
        clock=time.time,
    ):
        self.log = intervention_log
        self.send_command = send_command
        self.runner = runner
        self.routing = Routing.load(routing_path)
        self.clock = clock

    def _intervention(self, pair, kind, link_key, t_start):
        targets = {"links": [link_key], "flows": []}
        return Intervention(
            id="%s:%s" % (pair, kind),
            t_start=t_start,
            actor="controller",
            action="%s:admin_down" % kind,
            targets=targets,
            blast_radius=radius_with_detour(self.routing, targets),
            routing_sha256=self.routing.sha256,
        )

    def _wait_consequence(self, after_seq, timeout_s):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for entry in list(self.runner.timeline):
                if entry["seq"] > after_seq and (
                    entry["envelope"] or entry["conservation"] or entry["act_rule"]
                ):
                    return entry
            time.sleep(0.05)
        return None

    def act(self, kind, link_key, pair, mode, late_timeout_s=10.0):
        if mode not in MODES:
            raise ValueError(mode)
        command = {"subject": SUBJECT[kind], "target": "org.dt4n:link-" + link_key}
        record = {"pair": pair, "kind": kind, "link": link_key, "mode": mode}
        t_decide = self.clock()
        seq_before = self.runner.seq
        if mode == "log_first":
            self.log.append(self._intervention(pair, kind, link_key, t_decide))
            record["t_log_wall"] = self.clock()
        record["t_post_wall"] = self.clock()
        record["post"] = self.send_command(command)
        if mode == "log_late":
            hit = self._wait_consequence(seq_before, late_timeout_s)
            record["late_after_seq"] = hit["seq"] if hit else None
            self.log.append(self._intervention(pair, kind, link_key, t_decide))
            record["t_log_wall"] = self.clock()
        record["t_decide_wall"] = t_decide
        return record

    @staticmethod
    def new_pair(prefix="ctl"):
        return "%s-%s" % (prefix, uuid.uuid4().hex[:8])
