"""Interval intervention and lease behavior on synthetic fixtures only."""
import pytest

from ml.intervention_log import MAX_OPEN_S, InMemoryInterventionLog, Intervention


ZONE = frozenset({"link-s1-s2"})


def make(kind, source_time, pair="RUN:admin_down"):
    return Intervention(
        id="%s:%s" % (pair, kind),
        t_start=source_time,
        actor="controller",
        action="%s:admin_down" % kind,
        targets={"links": ["s1-s2"]},
        blast_radius=ZONE,
        routing_sha256="x" * 64,
    )


def test_sustained_intervention_covers_the_whole_interval():
    log = InMemoryInterventionLog()
    log.append(make("inject", 20.0))
    log.append(make("revert", 40.0))
    for source_time in (20.0, 24.0, 28.0, 33.0, 39.9, 40.0, 47.9):
        assert log.active(source_time, 8.0), source_time
    assert not log.active(19.9, 8.0)
    assert not log.active(48.0, 8.0)


def test_open_intervention_stops_when_lease_expires():
    log = InMemoryInterventionLog()
    log.append(make("inject", 100.0))
    assert log.active(100.0, 8.0)
    assert log.active(100.0 + MAX_OPEN_S - 0.1, 8.0)
    assert not log.active(100.0 + MAX_OPEN_S, 8.0)


def test_expired_open_lease_is_exposed_not_silent():
    log = InMemoryInterventionLog()
    log.append(make("inject", 100.0))
    assert log.stale_open(100.0 + 10.0) == []
    assert len(log.stale_open(100.0 + MAX_OPEN_S)) == 1


def test_transient_revert_alone_is_unchanged():
    log = InMemoryInterventionLog()
    log.append(make("revert", 40.0, pair="RUN:flood"))
    assert log.active(40.0, 8.0) and log.active(47.9, 8.0)
    assert not log.active(48.0, 8.0)


def test_append_only_still_rejects_duplicate_id():
    log = InMemoryInterventionLog()
    log.append(make("inject", 20.0))
    with pytest.raises(ValueError, match="append-only"):
        log.append(make("inject", 25.0))
