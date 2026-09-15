#!/usr/bin/env python3
"""Fault scenarios injected directly into Mininet, never through Ditto.

Why this path is separate from the Command Agent:
  1. Audit cleanliness: command audit logs must contain agent actions only.
  2. No leakage: the agent must infer faults from metrics, not Ditto messages.
  3. D5 staleness: faults happen in the real network at a clean t=0; only the
     observation is delayed by the twin pipeline.
"""

import time
from abc import ABC, abstractmethod

from mininet.tc_filter import install_tc_warning_filter
from mininet.topology_meta import baseline_bw, canonical, toggleable_links


install_tc_warning_filter()

DEFAULT_DELAY = '2ms'
IPERF_PORT = 5001
FLOOD_PORT = 5003


class Scenario(ABC):
    @classmethod
    @abstractmethod
    def params_from_seed(cls, rng, spec):
        """Build a deterministic scenario from an injected RNG and topology spec."""

    @abstractmethod
    def apply(self, net):
        """Inject the fault. Caller must hold net_lock."""

    @abstractmethod
    def revert(self, net):
        """Undo this scenario. Must be idempotent."""

    def describe(self):
        public = {
            key: value for key, value in self.__dict__.items()
            if not key.startswith('_')
        }
        return {'type': type(self).__name__, **public}


class LinkDegrade(Scenario):
    """Throttle one non-bridge link to baseline * (1 - factor)."""

    def __init__(self, link_key, factor, delay, baseline):
        self.link_key = link_key
        self.factor = float(factor)
        self.delay = delay
        self.baseline = float(baseline)
        self._applied = False

    @classmethod
    def params_from_seed(cls, rng, spec):
        candidates = toggleable_links(spec)
        if not candidates:
            raise ValueError('no toggleable links available for LinkDegrade')
        link_key = _choice(rng, candidates)
        factor = float(rng.uniform(0.2, 0.6))
        bw0 = baseline_bw(spec)[link_key]
        return cls(link_key, factor, DEFAULT_DELAY, bw0)

    def _find_link(self, net):
        for link in net.links:
            a = link.intf1.node.name
            b = link.intf2.node.name
            if canonical(a, b) == self.link_key:
                return link
        return None

    def apply(self, net):
        link = self._find_link(net)
        if link is None:
            raise ValueError('link not found: %s' % self.link_key)
        new_bw = max(1.0, self.baseline * (1.0 - self.factor))
        cfg = {'bw': new_bw, 'delay': self.delay}
        link.intf1.config(**cfg)
        link.intf2.config(**cfg)
        link.dt4n_bw = new_bw
        self._applied = True

    def revert(self, net):
        link = self._find_link(net)
        if link is None:
            return
        cfg = {'bw': self.baseline, 'delay': self.delay}
        link.intf1.config(**cfg)
        link.intf2.config(**cfg)
        link.dt4n_bw = self.baseline
        self._applied = False


class TrafficFlood(Scenario):
    """Start a UDP flood between one client and one server."""

    def __init__(self, src, dst, rate_mbps):
        self.src = src
        self.dst = dst
        self.rate_mbps = int(rate_mbps)
        self._applied = False

    @classmethod
    def params_from_seed(cls, rng, spec):
        clients = [
            h['name'] for h in spec.get('hosts', [])
            if isinstance(h, dict) and h.get('role') == 'client'
        ]
        servers = [
            h['name'] for h in spec.get('hosts', [])
            if isinstance(h, dict) and h.get('role') == 'server'
        ]
        if not clients or not servers:
            raise ValueError('TrafficFlood needs at least one client and server')
        src = _choice(rng, clients)
        dst = _choice(rng, servers)
        rate = int(rng.integers(30, 61))
        return cls(src, dst, rate)

    def apply(self, net):
        self.revert(net)
        src = net.get(self.src)
        dst = net.get(self.dst)
        dst.cmd('iperf -s -u -p %d > /tmp/flood_srv_%s.log 2>&1 &'
                % (FLOOD_PORT, self.dst))
        time.sleep(0.3)
        src.cmd('iperf -c %s -u -b %dM -p %d -t 100000 '
                '> /tmp/flood_cli_%s.log 2>&1 &'
                % (dst.IP(), self.rate_mbps, FLOOD_PORT, self.src))
        self._applied = True

    def revert(self, net):
        for name in (self.src, self.dst):
            net.get(name).cmd(
                'pkill -f "iperf.*%d" 2>/dev/null' % FLOOD_PORT)
        self._applied = False


class LinkDown(LinkDegrade):
    """Cut one non-bridge link almost completely.

    This is the severe end of LinkDegrade. We keep a tiny bandwidth floor via
    LinkDegrade.apply() because bw=0 can upset Linux tc/Mininet configuration.
    """

    @classmethod
    def params_from_seed(cls, rng, spec):
        candidates = toggleable_links(spec)
        if not candidates:
            raise ValueError('no toggleable links available for LinkDown')
        link_key = _choice(rng, candidates)
        factor = float(rng.uniform(0.97, 0.99))
        bw0 = baseline_bw(spec)[link_key]
        return cls(link_key, factor, DEFAULT_DELAY, bw0)


class CongestionShift(Scenario):
    """Degrade one link and add UDP load so the bottleneck shifts elsewhere."""

    def __init__(self, degrade_link, factor, delay, baseline,
                 flood_src, flood_dst, rate_mbps):
        self.degrade_link = degrade_link
        self.factor = float(factor)
        self.delay = delay
        self.baseline = float(baseline)
        self.flood_src = flood_src
        self.flood_dst = flood_dst
        self.rate_mbps = int(rate_mbps)
        self._applied = False

    @classmethod
    def params_from_seed(cls, rng, spec):
        candidates = toggleable_links(spec)
        clients = [
            h['name'] for h in spec.get('hosts', [])
            if isinstance(h, dict) and h.get('role') == 'client'
        ]
        servers = [
            h['name'] for h in spec.get('hosts', [])
            if isinstance(h, dict) and h.get('role') == 'server'
        ]
        if not candidates or not clients or not servers:
            raise ValueError(
                'CongestionShift needs links plus client/server hosts')
        degrade_link = _choice(rng, candidates)
        factor = float(rng.uniform(0.4, 0.6))
        bw0 = baseline_bw(spec)[degrade_link]
        src = _choice(rng, clients)
        dst = _choice(rng, servers)
        rate = int(rng.integers(20, 41))
        return cls(degrade_link, factor, DEFAULT_DELAY, bw0, src, dst, rate)

    def _find_link(self, net):
        for link in net.links:
            a = link.intf1.node.name
            b = link.intf2.node.name
            if canonical(a, b) == self.degrade_link:
                return link
        return None

    def apply(self, net):
        link = self._find_link(net)
        if link is None:
            raise ValueError('link not found: %s' % self.degrade_link)

        new_bw = max(1.0, self.baseline * (1.0 - self.factor))
        cfg = {'bw': new_bw, 'delay': self.delay}
        link.intf1.config(**cfg)
        link.intf2.config(**cfg)
        link.dt4n_bw = new_bw

        self.revert_flood(net)
        src = net.get(self.flood_src)
        dst = net.get(self.flood_dst)
        dst.cmd('iperf -s -u -p %d > /tmp/shift_srv_%s.log 2>&1 &'
                % (FLOOD_PORT, self.flood_dst))
        time.sleep(0.3)
        src.cmd('iperf -c %s -u -b %dM -p %d -t 100000 '
                '> /tmp/shift_cli_%s.log 2>&1 &'
                % (dst.IP(), self.rate_mbps, FLOOD_PORT, self.flood_src))
        self._applied = True

    def revert_flood(self, net):
        for name in (self.flood_src, self.flood_dst):
            net.get(name).cmd(
                'pkill -f "iperf.*%d" 2>/dev/null' % FLOOD_PORT)

    def revert(self, net):
        self.revert_flood(net)
        link = self._find_link(net)
        if link is not None:
            cfg = {'bw': self.baseline, 'delay': self.delay}
            link.intf1.config(**cfg)
            link.intf2.config(**cfg)
            link.dt4n_bw = self.baseline
        self._applied = False


SCENARIO_TYPES = [LinkDegrade, TrafficFlood, LinkDown, CongestionShift]


def _rng_from_seed(seed):
    try:
        from numpy.random import default_rng
    except ImportError as exc:
        raise RuntimeError(
            'numpy is required for reproducible scenario generation. '
            'Install numpy in the interpreter that runs experiments.'
        ) from exc
    return default_rng(seed)


def _choice(rng, items):
    return items[int(rng.integers(len(items)))]


def make_scenario(seed, spec, rng=None):
    """Create one deterministic scenario for TwinEnv.reset(seed)."""
    local_rng = rng if rng is not None else _rng_from_seed(seed)
    cls = SCENARIO_TYPES[int(local_rng.integers(len(SCENARIO_TYPES)))]
    return cls.params_from_seed(local_rng, spec)
