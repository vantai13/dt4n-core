"""Goi phat hanh detector: mot cua duy nhat lap rap scorer va FSM."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ml import campaign as C
from ml.fsm import DetectorFSM, FSMParams
from ml.model import EnvelopeModel
from ml.payload import alarm_payload
from ml.serve import ConservationLayer
from ml.serve_fast import FastOnlineScorer

SCHEMA = "DT4N-DETECTOR-RELEASE-1"


class ReleaseError(ValueError):
    """Goi phat hanh hong: tu choi, khong tu chua."""


@dataclass(frozen=True)
class DetectorRelease:
    content: dict
    sha256: str
    model: EnvelopeModel
    conservation: ConservationLayer

    @classmethod
    def load(cls, path) -> "DetectorRelease":
        path = Path(path)
        doc = json.loads(path.read_text(encoding="utf-8"))
        content = doc.get("content")
        if not isinstance(content, dict) or content.get("schema") != SCHEMA:
            raise ReleaseError("sai schema release")
        digest = C.sha256_bytes(C.canonical_json(content).encode("utf-8"))
        if digest != doc.get("content_sha256"):
            raise ReleaseError("release bi sua: hash lech")
        components = content["components"]
        model = EnvelopeModel.load(C.ROOT / components["envelope"]["path"])
        if model.content_sha256 != components["envelope"]["content_sha256"]:
            raise ReleaseError("envelope artifact khong khop release")
        conservation = ConservationLayer.load(
            C.ROOT / components["conservation"]["path"]
        )
        if conservation.amendment_sha256 != components["conservation"]["content_sha256"]:
            raise ReleaseError("conservation khong khop release")
        if content["conservation_mode"] not in ("active", "shadow"):
            raise ReleaseError("conservation_mode khong hop le")
        return cls(
            content=content,
            sha256=digest,
            model=model,
            conservation=conservation,
        )

    @property
    def version(self) -> str:
        return self.content["version"]

    def build(self, log=None):
        """Tra mot scorer va FSM moi cho mot luong snapshot lien tuc."""
        scorer = FastOnlineScorer(
            self.model,
            expected_collector_version=self.content["collector_version"],
            warmup_ticks=int(self.content["warmup_ticks"]),
            conservation=self.conservation,
            conservation_mode=self.content["conservation_mode"],
        )
        fsm = DetectorFSM(FSMParams(**self.content["fsm_params"]), log)
        return scorer, fsm

    def payload(self, transition, reading, *, detected_at: str) -> dict:
        """Payload truy vet chi sao chep bang chung cua chinh tick do."""
        if reading.t_source != transition.t_source:
            raise ReleaseError("reading va transition khong cung tick")
        body = alarm_payload(transition, self.model, detected_at=detected_at)
        active = self.content["conservation_mode"] == "active"
        body.update(
            {
                "releaseVersion": self.version,
                "releaseSha256": self.sha256,
                "conservationSha256": self.conservation.amendment_sha256,
                "evidence": {
                    "envelope": bool(reading.envelope_suspect),
                    "conservation": bool(active and reading.cons_alarm),
                    "act_rule": bool(reading.act),
                },
            }
        )
        return body
