"""Stub cho `mininet.node` -- xem _stub.py."""
from mininet._absent_mininet._stub import _NeedsRealMininet


class OVSSwitch(_NeedsRealMininet):
    _WHAT = "mininet.node.OVSSwitch"


class OVSBridge(_NeedsRealMininet):
    _WHAT = "mininet.node.OVSBridge"


class RemoteController(_NeedsRealMininet):
    _WHAT = "mininet.node.RemoteController"
