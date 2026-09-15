"""Stub cho `mininet.link` -- xem _stub.py."""
from mininet._absent_mininet._stub import _NeedsRealMininet


class Link(_NeedsRealMininet):
    _WHAT = "mininet.link.Link"


class TCLink(_NeedsRealMininet):
    _WHAT = "mininet.link.TCLink"
