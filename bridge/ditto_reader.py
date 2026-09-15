#!/usr/bin/env python3
"""Read DT4N twin snapshots from Ditto for Python agents.

This is the read-side counterpart of pusher.py. It intentionally does not keep
an SSE/WebSocket cache: fetch latency and Age of Information are research
variables in this project, so hiding them behind an extra cache would add a
confounder to D5 (staleness).
"""

import logging
import time

try:
    import requests
except ImportError:  # Keep pure helpers importable in minimal test envs.
    requests = None

from bridge.ditto_common import (
    DITTO_BASE_URL, DITTO_AUTH, NAMESPACE,
    make_thing_id_host, make_thing_id_link, make_thing_id_path,
    make_thing_id_switch,
)


log = logging.getLogger('ditto_reader')

READ_TIMEOUT = 1.0
READ_RETRY = 1
READ_RETRY_SLEEP = 0.2

RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
PERMANENT_STATUSES = {400, 401, 403, 404}
CLOCK_TOLERANCE = 0.05


def _require_requests():
    if requests is None:
        raise RuntimeError(
            'requests is required for Ditto reads. Use /usr/bin/python3 or '
            'install requests in this interpreter.'
        )
    return requests


def make_session():
    """Create a keep-alive HTTP session for repeated GET requests."""
    req = _require_requests()
    session = req.Session()
    session.auth = DITTO_AUTH
    return session


def extract_t_source(thing_body):
    """Return features.meta.properties.tSource as float, or None."""
    try:
        return float(thing_body['features']['meta']['properties']['tSource'])
    except (KeyError, TypeError, ValueError):
        return None


def compute_aoi(things, t_read, read_times=None):
    """Pure function: return {thing_id: t_observed - tSource}.

    Direct GET snapshots are read sequentially, so each Thing has its own
    observation time. Use read_times[thing_id] when available and fall back to
    t_read for cached/search results. Missing tSource is omitted. Negative AoI
    is returned and logged, not clipped, so clock skew or timestamp bugs remain
    visible.
    """
    read_times = read_times or {}
    out = {}
    for tid, body in things.items():
        t_source = extract_t_source(body)
        if t_source is None:
            continue
        t_obs = read_times.get(tid, t_read)
        aoi = t_obs - t_source
        if aoi < -CLOCK_TOLERANCE:
            log.warning(
                'Negative AoI %.3fs for %s (tSource=%.3f, t_obs=%.3f)',
                aoi, tid, t_source, t_obs,
            )
        out[tid] = aoi
    return out


def aoi_summary(aoi_map):
    """Pure compact statistics for env info."""
    if not aoi_map:
        return {'mean': None, 'max': None, 'n': 0, 'n_negative': 0}
    values = list(aoi_map.values())
    return {
        'mean': sum(values) / len(values),
        'max': max(values),
        'n': len(values),
        'n_negative': sum(1 for value in values if value < -CLOCK_TOLERANCE),
    }


def _request_exceptions():
    req = _require_requests()
    return (req.exceptions.Timeout, req.exceptions.ConnectionError)


def _get_one(session, thing_id):
    """GET one Thing. Return (body_or_none, ok)."""
    req = _require_requests()
    url = '%s/things/%s' % (DITTO_BASE_URL, thing_id)
    for attempt in range(READ_RETRY + 1):
        try:
            response = session.get(url, timeout=READ_TIMEOUT)
            if response.status_code == 200:
                return response.json(), True
            if response.status_code in PERMANENT_STATUSES:
                log.warning('GET %s -> %d (permanent)', thing_id,
                            response.status_code)
                return None, False
            if response.status_code not in RETRY_STATUSES:
                log.warning('GET %s -> %d', thing_id, response.status_code)
                return None, False
        except _request_exceptions() as exc:
            log.debug('GET %s transient error: %s', thing_id, exc)

        if attempt < READ_RETRY:
            time.sleep(READ_RETRY_SLEEP)
    return None, False


def fetch_all_things(session, thing_ids):
    """Read Things by direct GET /things/{id}, one request per Thing.

    Returns (things, meta). Each successfully read Thing gets an individual
    read time in meta['read_times']; meta['t_read'] is the conservative end time
    of the whole snapshot fetch.
    """
    things = {}
    read_times = {}
    n_ok = 0
    n_fail = 0
    t0_perf = time.perf_counter()

    for thing_id in thing_ids:
        body, ok = _get_one(session, thing_id)
        t_now = time.time()
        if ok and body is not None:
            things[thing_id] = body
            read_times[thing_id] = t_now
            n_ok += 1
        else:
            n_fail += 1

    t1 = time.time()
    t1_perf = time.perf_counter()
    return things, {
        't_read': t1,
        'read_times': read_times,
        'fetch_ms': (t1_perf - t0_perf) * 1000.0,
        'n_ok': n_ok,
        'n_fail': n_fail,
    }


def fetch_all_things_search(session, namespace=NAMESPACE, page_size=200):
    """Read Things via /search/things for benchmarking, not default env use."""
    _require_requests()
    url = '%s/search/things' % DITTO_BASE_URL
    things = {}
    cursor = None
    guard = 0
    t0_perf = time.perf_counter()

    try:
        while True:
            options = ['size(%d)' % page_size]
            if cursor:
                options.append('cursor(%s)' % cursor)
            params = {
                'filter': 'like(thingId,"%s:*")' % namespace,
                'option': ','.join(options),
            }
            response = session.get(url, params=params, timeout=READ_TIMEOUT)
            if response.status_code != 200:
                t1 = time.time()
                t1_perf = time.perf_counter()
                return {}, {
                    't_read': t1,
                    'fetch_ms': (t1_perf - t0_perf) * 1000.0,
                    'n_ok': 0,
                    'n_fail': 1,
                    'read_times': {},
                }

            data = response.json()
            for item in data.get('items', []):
                tid = item.get('thingId')
                if tid:
                    things[tid] = item
            cursor = data.get('cursor')
            guard += 1
            if not cursor or guard >= 100:
                break
    except _request_exceptions() as exc:
        t1 = time.time()
        t1_perf = time.perf_counter()
        log.warning('search read failed: %s', exc)
        return {}, {
            't_read': t1,
            'fetch_ms': (t1_perf - t0_perf) * 1000.0,
            'n_ok': 0,
            'n_fail': 1,
            'read_times': {},
        }

    t1 = time.time()
    t1_perf = time.perf_counter()
    return things, {
        't_read': t1,
        'fetch_ms': (t1_perf - t0_perf) * 1000.0,
        'n_ok': len(things),
        'n_fail': 0,
        'read_times': {},
    }


class SnapshotCache:
    """Forward-fill reader cache for transient Ditto read failures."""

    MAX_CONSECUTIVE_FAILS = 3

    def __init__(self):
        self._last = {}
        self._last_meta = {}
        self._consecutive_fails = 0

    def update(self, things, meta):
        n_expected = meta.get('n_ok', 0) + meta.get('n_fail', 0)
        all_failed = meta.get('n_ok', 0) == 0 and n_expected > 0
        if all_failed:
            self._consecutive_fails += 1
            return

        self._consecutive_fails = 0
        self._last.update(things)
        self._last_meta = dict(meta)

    def get(self, things, meta):
        self.update(things, meta)
        merged = dict(self._last)
        merged.update(things)
        stale_ids = sorted(tid for tid in merged if tid not in things)
        has_failed_reads = meta.get('n_fail', 0) > 0
        return merged, {
            'data_fresh': 0.0 if (has_failed_reads or stale_ids) else 1.0,
            'aborted': self._consecutive_fails >= self.MAX_CONSECUTIVE_FAILS,
            'stale_ids': stale_ids,
            'consecutive_fails': self._consecutive_fails,
        }

    def reset(self):
        self._last.clear()
        self._last_meta = {}
        self._consecutive_fails = 0


def fetch_snapshot(session, thing_ids, cache=None):
    """Read a snapshot and return (things, info) for TwinEnv."""
    things, meta = fetch_all_things(session, thing_ids)
    read_times = meta.get('read_times', {})
    if cache is not None:
        things, cache_info = cache.get(things, meta)
    else:
        cache_info = {
            'data_fresh': 1.0 if meta['n_fail'] == 0 else 0.0,
            'aborted': False,
            'stale_ids': [],
            'consecutive_fails': 0,
        }

    aoi = compute_aoi(things, meta['t_read'], read_times=read_times)
    info = dict(meta)
    info.pop('read_times', None)
    info.update(cache_info)
    info['aoi'] = aoi
    info['aoi_summary'] = aoi_summary(aoi)
    info['snapshot_span_s'] = meta.get('fetch_ms', 0.0) / 1000.0
    return things, info


def expected_thing_ids(spec, include_controller=False):
    """Return canonical Thing ids needed by the future agent.

    Default count for current topology: 17 = 5 hosts + 3 switches + 8 links
    + 1 path probe. The controller inbox Thing is intentionally omitted.
    """
    ids = []
    for host in spec.get('hosts', []):
        ids.append(make_thing_id_host(host['name']))
    for switch in spec.get('switches', []):
        ids.append(make_thing_id_switch(switch['name']))

    seen = set()
    for a, b in spec.get('links', []):
        tid = make_thing_id_link(a, b)
        if tid in seen:
            continue
        seen.add(tid)
        ids.append(tid)

    ids.append(make_thing_id_path('h1', 'srv1'))
    if include_controller:
        ids.append('%s:controller' % NAMESPACE)
    return ids
