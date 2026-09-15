#!/usr/bin/env python3
"""Reusable Mininet/Ditto lifecycle component for future Gym environments.

`run_sync.py` is an entry point: it parses CLI flags, dispatches measurement
modes, and may block in the Mininet CLI. EnvRunner is the shared component under
that entry point and the future TwinEnv: it owns the live net, background sync
threads, and reset hygiene.
"""

import json
import logging
import subprocess
import threading
import time
from collections import deque
from bridge.ditto_reader import expected_thing_ids
from mininet.aoi_norm import (
    AOI_NORM_DIVISOR,
    AOI_PERCENTILE,
    dynamic_thing_ids,
)
from mininet.tc_filter import install_tc_warning_filter
from mininet.topology_meta import baseline_bw, canonical, load_spec
from rl.injection import InjectionChannel


install_tc_warning_filter()

log = logging.getLogger('env_runner')

IPERF_PROCESS_PATTERN = '[i]perf'


class EnvRunner:
    """Own the DT4N live network and reset it for RL-style episodes."""

    def __init__(self, spec_path='ditto/topology_spec.json',
                 policy_path='ditto/policy.json',
                 sync_period=1.0, clients=3,
                 bw_backbone=20.0, bw_bottleneck=5.0,
                 convergence_timeout=8.0, do_pingall=False,
                 ping_every=20, reconcile_every=30,
                 steady_cycles=5, steady_tol=0.05,
                 steady_timeout=20.0, steady_min_norm=0.01,
                 hard_every=20, mininet_log_level='warning',
                 iperf_leak_tolerance=4,
                 fresh_aoi_norm_threshold=0.5,
                 fresh_timeout=None):
        self.spec_path = spec_path
        self.spec = load_spec(spec_path)
        self.policy_path = policy_path
        self.sync_period = sync_period
        self.clients = clients
        self.bw_backbone = bw_backbone
        self.bw_bottleneck = bw_bottleneck
        self.convergence_timeout = convergence_timeout
        self.do_pingall = do_pingall
        self.ping_every = ping_every
        self.reconcile_every = reconcile_every
        self.baseline_bw = baseline_bw(self.spec, bw_backbone, bw_bottleneck)

        self.steady_cycles = steady_cycles
        self.steady_tol = steady_tol
        self.steady_timeout = steady_timeout
        self.steady_min_norm = steady_min_norm
        self.hard_every = hard_every
        self.mininet_log_level = mininet_log_level
        self.iperf_leak_tolerance = int(iperf_leak_tolerance)
        self.fresh_aoi_norm_threshold = float(fresh_aoi_norm_threshold)
        self.fresh_timeout = fresh_timeout

        self.net = None
        self.net_lock = threading.RLock()
        self.stop_event = threading.Event()
        self._sync_thread = None
        self._command_thread = None
        self._background_hosts = ()
        self.injection = None

        self.session = None
        self.thing_ids = expected_thing_ids(self.spec)
        self.dynamic_thing_ids = dynamic_thing_ids(self.spec)

        self._episode_count = 0
        self._iperf_baseline = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self):
        """Build Mininet, bootstrap Ditto Things, and start sync/command threads."""
        if self.net is not None:
            raise RuntimeError('EnvRunner.start() called while net is already live')
        from mininet.log import info, setLogLevel
        from mininet.topology import build_net, start_net

        if self.mininet_log_level:
            setLogLevel(self.mininet_log_level)

        log.info('EnvRunner.start()')
        t0 = time.monotonic()
        from bridge.bootstrap import bootstrap_all, entities_from_net
        from bridge.command_agent import run as command_run
        from bridge.ditto_reader import make_session
        from bridge.sync_agent import run as sync_run

        self.session = make_session()
        self.stop_event.clear()

        self.net = build_net(clients=self.clients,
                             bw_backbone=self.bw_backbone,
                             bw_bottleneck=self.bw_bottleneck)
        start_net(self.net, convergence_timeout=self.convergence_timeout,
                  do_pingall=self.do_pingall)
        self.injection = InjectionChannel(self.net, self.net_lock)

        info('*** Bootstrap Things lên Ditto\n')
        with open(self.policy_path, encoding='utf-8') as f:
            policy = json.load(f)
        bootstrap_all(entities_from_net(self.net), policy, mode='create')

        info('*** Khởi động Sync Agent (thread nền)\n')
        self._sync_thread = threading.Thread(
            target=sync_run,
            args=(self.net,),
            kwargs={
                'period': self.sync_period,
                'ping_every': self.ping_every,
                'reconcile_every': self.reconcile_every,
                'net_lock': self.net_lock,
                'stop_event': self.stop_event,
            },
            daemon=True,
        )
        self._sync_thread.start()

        info('*** Khởi động Command Agent (thread nền) — nghe lệnh chiều xuống\n')
        self._command_thread = threading.Thread(
            target=command_run,
            kwargs={
                'net': self.net,
                'net_lock': self.net_lock,
                'stop_event': self.stop_event,
            },
            daemon=True,
        )
        self._command_thread.start()

        time.sleep(max(2.0, self.sync_period * 3))
        startup_iperf = self._count_iperf()
        self._iperf_baseline = None
        log.info('EnvRunner started in %.1fs, startup iperf=%d; '
                 'episode iperf baseline pending',
                 time.monotonic() - t0, startup_iperf)
        return self.net

    def close(self, cleanup_mn=False):
        """Stop background threads, kill traffic, and stop Mininet.

        ``mn -c`` also kills ``ryu-manager``. Keep it opt-in so periodic hard
        resets during training do not tear down the external controller.
        """
        self.stop_event.set()
        for thread in (self._sync_thread, self._command_thread):
            if thread is not None:
                thread.join(timeout=5)
        self._sync_thread = None
        self._command_thread = None

        if self.net is not None:
            from mininet.log import info

            log.info('EnvRunner.close(): stopping Mininet')
            info('*** Tắt mạng\n')
            with self.net_lock:
                if self.injection is not None:
                    self.injection.revert_all()
                self._kill_iperf()
                self.net.stop()
            self.net = None
            self.injection = None
            self._background_hosts = ()

        if cleanup_mn:
            try:
                subprocess.run(['mn', '-c'], capture_output=True, check=False)
            except OSError as exc:
                log.warning('mn -c skipped: %s', exc)

    def hard_reset(self):
        """Fully rebuild the network. Clean, slower, and used as a periodic drain."""
        log.info('HARD reset')
        t0 = time.monotonic()
        self.close(cleanup_mn=False)
        self.start()
        return time.monotonic() - t0

    # ------------------------------------------------------------------
    # Episode reset
    # ------------------------------------------------------------------
    def soft_reset(self, scenario=None):
        """Clean episode leftovers without rebuilding Mininet.

        Returns an info dict with reset timing and dirty flags. Future TwinEnv
        should put these values into Gym `info`.
        """
        if self.net is None:
            raise RuntimeError('EnvRunner.soft_reset() called before start()')

        t0 = time.monotonic()
        timings = {}
        self._episode_count += 1
        mode = 'soft'

        if self.hard_every and self._episode_count % self.hard_every == 0:
            timings['hard_reset'] = self.hard_reset()
            mode = 'hard'
        else:
            if self.injection is not None:
                t = time.monotonic()
                self.injection.revert_all()
                timings['revert_scenarios'] = time.monotonic() - t

            with self.net_lock:
                t = time.monotonic()
                self._kill_iperf()
                timings['kill_iperf'] = time.monotonic() - t

                t = time.monotonic()
                self._restore_links()
                timings['restore_links'] = time.monotonic() - t

                t = time.monotonic()
                self._flush_arp()
                timings['flush_arp'] = time.monotonic() - t

                t = time.monotonic()
                self._reset_collector_cache()
                timings['reset_cache'] = time.monotonic() - t

        t = time.monotonic()
        self._start_episode_traffic()
        timings['start_traffic'] = time.monotonic() - t

        ok, waited = self._wait_steady_state()
        timings['steady_wait'] = waited

        fresh_push_ok, fresh_push_s, fresh_push_ok_n, fresh_push_total = (
            self._refresh_twin_snapshot()
        )
        timings['refresh_twin'] = fresh_push_s

        fresh_ok, fresh_waited, fresh_aoi_norm = self._wait_data_fresh()
        timings['data_fresh_wait'] = fresh_waited

        # HEALTH GATE: mang-NEN phai khoe TRUOC khi inject su co.
        # Dat o day, khong dat sau inject: sau inject mang "om" la dung.
        t = time.monotonic()
        health = self.assert_baseline_healthy()
        timings['health_gate'] = time.monotonic() - t

        if scenario is not None:
            if self.injection is None:
                self.injection = InjectionChannel(self.net, self.net_lock)
            self.injection.apply(scenario)

        n_iperf = self._count_iperf()
        leaked = self._iperf_leaked(n_iperf)
        total = time.monotonic() - t0
        info_dict = {
            'reset_mode': mode,
            'reset_total_s': total,
            'reset_steady_ok': ok,
            'reset_wait_s': waited,
            'reset_fresh_push_ok': fresh_push_ok,
            'reset_fresh_push_ok_n': fresh_push_ok_n,
            'reset_fresh_push_total': fresh_push_total,
            'reset_fresh_ok': fresh_ok,
            'reset_aoi_norm': fresh_aoi_norm,
            'reset_dirty': (not ok) or (not fresh_ok) or leaked,
            'iperf_count': n_iperf,
            'iperf_baseline': self._iperf_baseline,
            'iperf_leaked': leaked,
            'health': health,
            'active_scenarios': (
                self.injection.active() if self.injection is not None else []
            ),
            'timings': timings,
        }
        if info_dict['reset_dirty']:
            log.warning('Reset dirty: steady_ok=%s fresh_ok=%s '
                        'aoi_norm=%s leaked=%s iperf=%d baseline=%s',
                        ok, fresh_ok, fresh_aoi_norm, leaked, n_iperf,
                        self._iperf_baseline)
        return info_dict

    def observe_raw(self, cache=None):
        """Read current Ditto Things for the future TwinEnv observation path."""
        from bridge.ditto_reader import fetch_snapshot, make_session

        if self.session is None:
            self.session = make_session()
        return fetch_snapshot(self.session, self.thing_ids, cache=cache)

    def send_command(self, cmd):
        """Send one agent action through the real Ditto -> Command Agent path.

        ``cmd`` is the dict returned by ``ActionSpace.to_command()``:
        ``{'subject': ..., 'target': ..., 'params': {...}}``.  This deliberately
        uses the front door instead of mutating Mininet directly, so whitelist,
        deduplication, audit logs, and command timing stay in the loop.
        """
        if cmd is None:
            return None

        import uuid
        import requests
        from bridge.command_agent import (
            CONTROLLER_THING_ID,
            DITTO_AUTH,
            DITTO_BASE_URL,
            HTTP_TIMEOUT,
        )

        subject = cmd.get('subject')
        target = cmd.get('target')
        if not subject or not target:
            raise ValueError('command requires subject and target: %r' % cmd)

        cid = str(uuid.uuid4())
        params = dict(cmd.get('params') or {})
        body = {'target': target, 'clientCorrelationId': cid}
        body.update(params)
        headers = {
            'Content-Type': 'application/json',
            'correlation-id': cid,
        }
        url = '%s/things/%s/inbox/messages/%s?timeout=0' % (
            DITTO_BASE_URL, CONTROLLER_THING_ID, subject)

        post_started = time.monotonic()
        result = {
            'cid': cid,
            'subject': subject,
            'target': target,
            'params': params,
            'http_status': None,
            'post_error': None,
            'post_ms': None,
        }
        try:
            response = requests.post(url, json=body, headers=headers,
                                     auth=DITTO_AUTH, timeout=HTTP_TIMEOUT)
            result['http_status'] = response.status_code
            if response.status_code not in (200, 201, 202, 204):
                result['post_error'] = response.text[:240]
        except requests.exceptions.RequestException as exc:
            result['post_error'] = '%s:%s' % (type(exc).__name__, exc)
            log.warning('send_command failed: %s', exc)
        finally:
            result['post_ms'] = (time.monotonic() - post_started) * 1000.0
        return result

    # ------------------------------------------------------------------
    # Traffic helpers
    # ------------------------------------------------------------------
    def start_server_background(self, rate_mbps=2.0, duration=100000):
        """Start only the srv1->srv2 UDP background used by run_sync CLI mode."""
        if self.net is None:
            raise RuntimeError('start_server_background() called before start()')
        if rate_mbps <= 0:
            return ()
        from mininet.traffic import start_server_to_server

        self._background_hosts = start_server_to_server(
            self.net, rate_mbps=rate_mbps, duration=duration)
        return self._background_hosts

    def _start_episode_traffic(self):
        """Start RL episode background traffic.

        start_background_load already starts the srv1->srv2 UDP flow in this
        repository, so do not start that flow a second time.
        """
        from mininet.traffic import start_background_load

        self._background_hosts = start_background_load(
            self.net, scenario='normal', duration=100000)
        return self._background_hosts

    # ------------------------------------------------------------------
    # Cleanup steps
    # ------------------------------------------------------------------
    def _kill_iperf(self):
        """Terminate all iperf/iperf3 processes visible on this testbed.

        Mininet hosts have their own network namespaces, but their processes
        still exist in the host process table. Keep cleanup and counting in the
        same scope: ask each host namespace to stop its iperf children, then
        also run a global pkill for any orphaned or externally spawned iperf.
        """
        if self.net is None:
            return

        for host in self.net.hosts:
            host.cmd('pkill -f iperf 2>/dev/null')
        subprocess.run(['pkill', '-f', IPERF_PROCESS_PATTERN],
                       capture_output=True, check=False)
        time.sleep(0.3)

        if self._count_iperf() > 0:
            for host in self.net.hosts:
                host.cmd('pkill -9 -f iperf 2>/dev/null')
            subprocess.run(['pkill', '-9', '-f', IPERF_PROCESS_PATTERN],
                           capture_output=True, check=False)
            time.sleep(0.3)

        remaining = self._count_iperf()
        if remaining:
            log.warning('iperf cleanup left %d process(es)', remaining)
        self._background_hosts = ()

    def _count_iperf(self):
        """Count iperf/iperf3 processes in the host process table."""
        result = subprocess.run(['pgrep', '-c', '-f', IPERF_PROCESS_PATTERN],
                                capture_output=True, check=False)
        try:
            return int(result.stdout.decode().strip() or 0)
        except ValueError:
            return 0

    def _iperf_leaked(self, n_iperf):
        """Return True when iperf count grows beyond normal episode traffic.

        The first soft reset starts the canonical episode traffic, so use that
        count as the baseline. Counting at ``start()`` is too early because the
        episode traffic is not running yet and would mark a healthy episode as
        dirty.
        """
        if self._iperf_baseline is None:
            self._iperf_baseline = int(n_iperf)
            log.info('Calibrated episode iperf baseline=%d',
                     self._iperf_baseline)
            return False
        return int(n_iperf) > self._iperf_baseline + self.iperf_leak_tolerance

    def _restore_links(self):
        """Bring every link up and restore baseline bandwidth plus original delay."""
        for link in self.net.links:
            a, b = link.intf1.node.name, link.intf2.node.name
            self.net.configLinkStatus(a, b, 'up')

            bw0 = self.baseline_bw.get(canonical(a, b))
            if bw0 is None:
                continue
            cfg = {'bw': float(bw0)}
            delay = getattr(link, 'dt4n_delay', None)
            if delay:
                cfg['delay'] = delay
            link.intf1.config(**cfg)
            link.intf2.config(**cfg)
            link.dt4n_bw = float(bw0)

    def _flush_arp(self):
        for host in self.net.hosts:
            host.cmd('ip -s -s neigh flush all 2>/dev/null')

    def _reset_collector_cache(self):
        collector = getattr(self.net, 'dt4n_collector', None)
        if collector is None:
            return
        for attr in ('_prev', '_prev_link'):
            value = getattr(collector, attr, None)
            if hasattr(value, 'clear'):
                value.clear()

    def _refresh_twin_snapshot(self):
        """Push one full fresh collector snapshot before the first observation.

        Delta sync intentionally ignores meta.tSource-only changes, so quiet
        Things may keep old timestamps until the next reconciliation cycle.
        A soft reset needs a fresh baseline observation now, not up to
        reconcile_every cycles later.
        """
        collector = getattr(self.net, 'dt4n_collector', None)
        if collector is None:
            return False, 0.0, 0, 0

        from bridge.adapter import collector_to_things
        from bridge.ditto_reader import make_session
        from bridge.pusher import patch_thing

        if self.session is None:
            self.session = make_session()

        t0 = time.monotonic()
        try:
            snapshot = collector.collect_all()
            things_now = collector_to_things(snapshot)
        except Exception as exc:
            elapsed = time.monotonic() - t0
            log.warning('fresh twin snapshot collect failed: %s', exc)
            return False, elapsed, 0, 0

        expected_ids = set(self.thing_ids)
        n_ok = 0
        n_total = 0
        for tid, data in things_now.items():
            if tid not in expected_ids:
                continue
            features = data.get('features', {})
            if not features:
                continue
            n_total += 1
            if patch_thing(tid, {'features': features}, session=self.session):
                n_ok += 1

        elapsed = time.monotonic() - t0
        ok = n_total > 0 and n_ok == n_total
        if not ok:
            log.warning('fresh twin snapshot pushed %d/%d Thing(s)',
                        n_ok, n_total)
        return ok, elapsed, n_ok, n_total

    # ------------------------------------------------------------------
    # Steady-state gate
    # ------------------------------------------------------------------
    def _read_throughput_norm(self):
        """Read server RX throughput from Ditto and normalize by backbone Mbps."""
        from bridge.ditto_reader import fetch_snapshot, make_session

        if self.session is None:
            self.session = make_session()
        things, _meta = fetch_snapshot(self.session, self.thing_ids)
        total_mbps = 0.0
        for name in ('srv1', 'srv2'):
            thing_id = 'org.dt4n:host-%s' % name
            try:
                props = things[thing_id]['features']['traffic']['properties']
                total_mbps += float(props.get('rxRate') or 0.0) * 8.0 / 1e6
            except (KeyError, TypeError, ValueError):
                pass
        return total_mbps / float(self.bw_backbone)

    def assert_baseline_healthy(self, thr_min=0.30, max_retries=2):
        """Health gate: mang-NEN (chua co su co) phai khoe.

        Goi trong soft_reset ngay truoc khi inject scenario. Neu mang nen
        khong khoe, hard_reset lai de tranh train tren env chet.
        """
        for attempt in range(max_retries + 1):
            thr = self._read_throughput_norm()
            if thr >= thr_min:
                return {
                    'throughput_norm': round(thr, 4),
                    'attempts': attempt,
                    'recovered_by_hard_reset': attempt > 0,
                }
            log.error('HEALTH GATE FAIL (attempt %d/%d): thr=%.3f < %.2f '
                      '-> hard_reset lai', attempt, max_retries, thr, thr_min)
            if attempt < max_retries:
                self.hard_reset()
                self._start_episode_traffic()
                self._wait_steady_state()

        raise RuntimeError(
            'HEALTH GATE: mang-nen van chet sau %d lan hard_reset (thr=%.3f). '
            'Dung train — dieu tra ha tang truoc.' % (max_retries, thr))

    def _wait_steady_state(self):
        """Wait until throughput is stable for consecutive sync cycles.

        rxRate is a one-cycle moving measurement. Immediately after iperf starts,
        the first samples include socket setup and TCP slow start. Returning an
        observation during that window makes s0 depend on Linux scheduling rather
        than the experiment seed.
        """
        hist = deque(maxlen=self.steady_cycles)
        t0 = time.monotonic()
        while time.monotonic() - t0 < self.steady_timeout:
            value = self._read_throughput_norm()
            hist.append(value)
            if len(hist) == self.steady_cycles:
                spread = max(hist) - min(hist)
                if spread < self.steady_tol and max(hist) >= self.steady_min_norm:
                    return True, time.monotonic() - t0
            time.sleep(self.sync_period)
        log.warning('steady state timeout after %.1fs', self.steady_timeout)
        return False, self.steady_timeout

    def _wait_data_fresh(self, max_aoi_norm=None, timeout=None):
        """Wait until the same aoi_norm used by the state vector is fresh."""
        if max_aoi_norm is None:
            max_aoi_norm = self.fresh_aoi_norm_threshold
        if timeout is None:
            timeout = (self.fresh_timeout if self.fresh_timeout is not None
                       else self.steady_timeout)

        t0 = time.monotonic()
        last_aoi_norm = None
        while time.monotonic() - t0 < timeout:
            _things, meta = self.observe_raw()
            last_aoi_norm = self._aoi_norm_p95(meta.get('aoi') or {})
            fresh = float(meta.get('data_fresh', 0.0) or 0.0)
            if fresh >= 1.0 and last_aoi_norm <= max_aoi_norm:
                return True, time.monotonic() - t0, last_aoi_norm
            time.sleep(self.sync_period)

        log.warning('data freshness timeout after %.1fs: '
                    'aoi_norm=%s threshold=%.3f',
                    timeout, last_aoi_norm, max_aoi_norm)
        return False, timeout, last_aoi_norm

    def _aoi_norm_p95(self, aoi_map):
        """Compute p95 AoI / divisor exactly like StateBuilderDraft."""
        values = []
        for tid, value in (aoi_map or {}).items():
            if tid not in self.dynamic_thing_ids or value is None:
                continue
            try:
                x = float(value)
            except (TypeError, ValueError):
                continue
            if x >= -0.05:
                values.append(x)

        if not values:
            return 0.0

        values.sort()
        if len(values) == 1:
            p95 = values[0]
        else:
            pos = AOI_PERCENTILE * (len(values) - 1)
            lo = int(pos)
            hi = min(lo + 1, len(values) - 1)
            frac = pos - lo
            p95 = values[lo] + frac * (values[hi] - values[lo])
        return min(max(p95 / AOI_NORM_DIVISOR, 0.0), 1.0)
