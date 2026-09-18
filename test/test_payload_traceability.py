import json

import pytest

from ml import campaign as C
from ml.model import EnvelopeModel
from ml.payload import REQUIRED, alarm_payload


@pytest.fixture(scope="module")
def model():
    return EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")


class FakeTransition:
    state, prev, changed = "suspect", "normal", True
    cause, reason, t_source, tick = None, "3 columns out of bounds", 1.0, 7
    suppressed_by = ()


def test_payload_carries_model_identity(model):
    payload = alarm_payload(FakeTransition(), model, detected_at="2026-09-18T01:00:00Z")
    assert payload["modelVersion"] == "envelope-1.0.0"
    assert payload["artifactSha256"] == model.content_sha256
    assert len(payload["artifactSha256"]) == 64
    assert all(payload.get(key) for key in REQUIRED)


def test_payload_refuses_when_reason_empty(model):
    transition = FakeTransition()
    transition.reason = ""
    with pytest.raises(ValueError, match="truy vet"):
        alarm_payload(transition, model, detected_at="2026-09-18T01:00:00Z")


def test_sha_in_payload_matches_file_on_disk(model):
    document = json.loads((C.ROOT / "models/envelope-1.0.0.json").read_text())
    assert model.content_sha256 == document["content_sha256"]
