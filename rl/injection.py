#!/usr/bin/env python3
"""Back-door scenario injection channel.

Command Agent is the front door for RL agent actions:
agent -> Ditto -> whitelist -> audit -> net.

InjectionChannel is the back door for experiments:
scenario -> net directly, with a separate logger and no Command Agent audit.
"""

import logging


log = logging.getLogger('injection')


class InjectionChannel:
    def __init__(self, net, net_lock):
        self.net = net
        self.net_lock = net_lock
        self._active = []

    def apply(self, scenario):
        """Inject one scenario while holding net_lock."""
        with self.net_lock:
            scenario.apply(self.net)
        self._active.append(scenario)
        log.info('INJECT %s', scenario.describe())
        return scenario

    def revert_all(self):
        """Revert all active scenarios. Safe to call repeatedly."""
        with self.net_lock:
            for scenario in reversed(self._active):
                scenario.revert(self.net)
        self._active.clear()

    def active(self):
        return [scenario.describe() for scenario in self._active]
