"""Build the detector payload handed to Phase 7.

The payload copies the FSM decision; it must never recompute state.  Every
non-normal detector message is traceable to one exact model artifact.
"""
from __future__ import annotations


REQUIRED = ("state", "reason", "detectedAt", "modelVersion", "artifactSha256")


def alarm_payload(transition, model, *, detected_at: str) -> dict:
    """Return a traceable payload without changing the FSM decision."""
    payload = {
        "state": transition.state,
        "reason": transition.reason,
        "cause": transition.cause,
        "detectedAt": detected_at,
        "modelVersion": model.version,
        "artifactSha256": model.content_sha256,
    }
    missing = [key for key in REQUIRED if not payload.get(key)]
    if missing:
        raise ValueError("payload thieu truong truy vet: %s" % missing)
    return payload
