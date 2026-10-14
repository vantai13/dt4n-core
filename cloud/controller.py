#!/usr/bin/env python3
"""
controller.py — Bộ điều khiển cloud (GĐ1.4): TWIN quyết định, actuator thực hiện.

Đúng chuỗi của thuyết minh ND4:
  "Digital Twin gửi tín hiệu đến script Controller, script này dùng thư viện AWS
   gọi API..."  ->  đọc Ditto  ->  decide()  ->  CloudActuator.set_capacity()

ĐỌC TỪ TWIN (KHÔNG hỏi thẳng AWS hay Mininet):
  org.dt4n:host-srv1      status.state (up/down), traffic.rxRate (B/s), meta.tSource
  org.dt4n:link-s2-srv1   capacity.bwMbps (dung lượng link vào srv1)
  org.dt4n:cloud-pool     capacity.desired, pool.healthy, meta.tSource, meta.pollOk

HAI LUẬT, mỗi luật là một "mức" 0/1, cộng lại thành số máy cloud mong muốn:
  load_level     : srv1 quá tải (ρ > 0.8) N_UP nhịp liền -> 1 ; nhàn (ρ < 0.3) N_DOWN nhịp liền -> 0
  failover_level : srv1 DOWN K_DOWN nhịp liền -> 1 (cloud bù cho srv1) ; UP lại K_UP nhịp -> 0
  target = min(MAX_SIZE, load_level + failover_level)

VÌ SAO "ĐẶT MỨC THEO TẢI" CHỨ KHÔNG "CÒN QUÁ TẢI THÌ +1":
  máy EC2 nằm khác mạng, KHÔNG gánh traffic của Mininet -> thêm máy không làm ρ của
  srv1 giảm. Nếu luật là "còn quá tải thì +1", nó sẽ tăng mãi tới trần. Đây là điều
  khiển THUẬN (feedforward: tải -> mức), khác vòng kín setBandwidth ở Phase 8.

AN TOÀN:
  - Debounce: cần nhiều nhịp liên tiếp mới đổi mức (chống nhiễu nhất thời).
  - Hysteresis: ngưỡng lên 0.8 khác ngưỡng xuống 0.3 (chống bật/tắt liên tục).
  - Bất đối xứng: THÊM máy ngay; BỚT máy chỉ khi đã qua cooldown 120 s.
  - Gác độ tươi: dữ liệu twin cũ quá ngưỡng -> HOLD, không hành động, không đếm nhịp.
  - Dry-run: in và ghi quyết định nhưng không gọi AWS ("đề xuất").

CÁCH CHẠY (từ thư mục gốc repo, KHÔNG cần sudo; Ditto + run_sync + cloud.collector đang chạy):
    python3 -m cloud.controller once               # một nhịp: in quan sát + quyết định
    python3 -m cloud.controller run --dry-run      # chạy liên tục, KHÔNG gọi AWS
    python3 -m cloud.controller run                # chạy thật
"""

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass

from bridge.ditto_common import make_thing_id_host, make_thing_id_link
from cloud import config as C
from cloud.twin import THING_ID as POOL_ID
from controller.audit import AuditLog

SRV1_ID = make_thing_id_host('srv1')                 # org.dt4n:host-srv1
LINK_ID = make_thing_id_link('s2', 'srv1')           # org.dt4n:link-s2-srv1
AUDIT_PATH = 'logs/cloud_controller_audit.jsonl'


@dataclass(frozen=True)
class Params:
    period_s: float = 2.0
    high: float = 0.8              # ρ > 0.8 : srv1 gần đầy
    low: float = 0.3               # ρ < 0.3 : srv1 nhàn
    n_up: int = 3                  # 3 nhịp liền quá tải -> cần thêm máy (~6 s)
    n_down: int = 15               # 15 nhịp liền nhàn -> có thể bớt (~30 s)
    k_down: int = 2                # srv1 down 2 nhịp liền -> bù máy (~4 s)
    k_up: int = 5                  # srv1 up lại 5 nhịp liền -> thôi bù (~10 s)
    cooldown_in_s: float = 120.0   # sau lần đổi gần nhất, chờ 120 s mới được BỚT máy
    # Sync agent chỉ gửi DELTA + đồng bộ toàn phần mỗi ~30 s (run_sync --reconcile-every 30).
    # srv1 đứng yên -> tSource của nó có thể cũ ~30 s mà hệ vẫn khỏe -> ngưỡng phải > 30 s.
    max_age_net_s: float = 45.0
    max_age_cloud_s: float = 20.0  # collector cloud đẩy mỗi 5 s -> 20 s = lỡ ~3 lần liền
    default_bw_mbps: float = 20.0  # topology.py: bw_backbone = 20 cho link srv1-s2


@dataclass(frozen=True)
class Obs:
    """Một lần nhìn twin. None = không đọc được."""
    srv1_state: str = None
    srv1_rx_Bps: float = None
    bw_mbps: float = None
    net_age_s: float = None
    cloud_desired: int = None
    cloud_healthy: int = None
    cloud_age_s: float = None
    cloud_poll_ok: bool = False


@dataclass(frozen=True)
class CState:
    high_streak: int = 0
    low_streak: int = 0
    down_streak: int = 0
    up_streak: int = 0
    load_level: int = 0
    failover_level: int = 0
    last_change_t: float = -1e18


# ===========================================================================
# PHẦN 1 — decide(): HÀM THUẦN. Không mạng, không AWS, không Ditto -> test được hết.
# ===========================================================================
def decide(s, o, p, now):
    """(trạng thái, quan sát, tham số, giờ) -> (trạng thái mới, target hoặc None, info).

    target = None nghĩa là HOLD: không đủ tin để quyết định, KHÔNG làm gì.
    Khi HOLD, trạng thái giữ nguyên: nhịp dữ liệu cũ không được tính vào streak.
    """
    if o.net_age_s is None or o.net_age_s > p.max_age_net_s:
        return s, None, {'code': 'hold_stale_net', 'net_age_s': o.net_age_s}
    if (not o.cloud_poll_ok or o.cloud_age_s is None
            or o.cloud_age_s > p.max_age_cloud_s or o.cloud_desired is None):
        return s, None, {'code': 'hold_stale_cloud', 'cloud_age_s': o.cloud_age_s}
    if o.srv1_state not in ('up', 'down') or o.srv1_rx_Bps is None:
        return s, None, {'code': 'hold_srv1_unknown', 'srv1_state': o.srv1_state}

    bw = o.bw_mbps if o.bw_mbps else p.default_bw_mbps
    rho = (o.srv1_rx_Bps * 8.0 / 1e6) / bw              # B/s -> Mbps, chia dung lượng

    high = s.high_streak + 1 if rho > p.high else 0
    low = s.low_streak + 1 if rho < p.low else 0
    down = s.down_streak + 1 if o.srv1_state == 'down' else 0
    up = s.up_streak + 1 if o.srv1_state == 'up' else 0

    load = 1 if high >= p.n_up else (0 if low >= p.n_down else s.load_level)
    fail = 1 if down >= p.k_down else (0 if up >= p.k_up else s.failover_level)
    target = min(C.MAX_SIZE, load + fail)

    code = 'ok'
    if target < o.cloud_desired and now - s.last_change_t < p.cooldown_in_s:
        target, code = o.cloud_desired, 'cooldown_scale_in'   # chưa được bớt máy

    last_change = now if target != o.cloud_desired else s.last_change_t
    new = CState(high, low, down, up, load, fail, last_change)
    return new, target, {'code': code, 'rho': round(rho, 3), 'load': load,
                         'failover': fail, 'target': target}


# ===========================================================================
# PHẦN 2 — đọc twin thành Obs
# ===========================================================================
def _prop(body, feature, key):
    try:
        return body['features'][feature]['properties'][key]
    except (KeyError, TypeError):
        return None


def observe(session):
    """GET 3 Thing từ Ditto -> Obs. Tuổi dữ liệu = lúc đọc - tSource của Thing đó."""
    from bridge.ditto_reader import extract_t_source, fetch_all_things
    things, meta = fetch_all_things(session, [SRV1_ID, LINK_ID, POOL_ID])
    rt = meta['read_times']
    host, link, pool = things.get(SRV1_ID), things.get(LINK_ID), things.get(POOL_ID)

    def age(tid, body):
        t = extract_t_source(body) if body else None
        return (rt[tid] - t) if (t and tid in rt) else None

    return Obs(
        srv1_state=_prop(host, 'status', 'state') if host else None,
        srv1_rx_Bps=_prop(host, 'traffic', 'rxRate') if host else None,
        bw_mbps=_prop(link, 'capacity', 'bwMbps') if link else None,
        net_age_s=age(SRV1_ID, host),
        cloud_desired=_prop(pool, 'capacity', 'desired') if pool else None,
        cloud_healthy=_prop(pool, 'pool', 'healthy') if pool else None,
        cloud_age_s=age(POOL_ID, pool),
        cloud_poll_ok=bool(_prop(pool, 'meta', 'pollOk')) if pool else False,
    )


# ===========================================================================
# PHẦN 3 — một nhịp điều khiển: nhìn -> quyết định -> (gọi actuator) -> ghi lại
# ===========================================================================
def default_push(thing_id, features):
    from bridge.pusher import patch_thing
    return patch_thing(thing_id, features)


class CloudController:
    def __init__(self, actuator, reader, params=Params(), audit_path=AUDIT_PATH,
                 push=default_push, wall=time.time):
        self.actuator, self.reader, self.p = actuator, reader, params
        self.audit = AuditLog(audit_path)
        self.push, self.wall = push, wall
        self.state = CState()
        self._last_key = None

    def step(self):
        now = self.wall()
        obs = self.reader()
        new, target, info = decide(self.state, obs, self.p, now)
        result = None
        if target is not None and target != obs.cloud_desired:
            # Twin có thể còn chậm vài giây sau lệnh trước (collector 5 s/lần).
            # Gửi lại cùng mức là AN TOÀN: actuator tự kiểm AWS và trả 'noop'.
            result = self.actuator.set_capacity(
                target, reason='%s load=%s failover=%s rho=%s' % (
                    info['code'], info.get('load'), info.get('failover'), info.get('rho')))
        self.state = new

        key = (info['code'], info.get('target'), info.get('load'), info.get('failover'))
        if key != self._last_key or result is not None:
            self.audit.append({'kind': 'decision', 't_wall': now, 'obs': asdict(obs),
                               'info': info, 'state': asdict(new),
                               'action': None if result is None else {
                                   'cid': result['cid'], 'outcome': result['outcome']}})
            self._last_key = key
            changed = True
        else:
            changed = False
        self._mirror(now, info)
        return obs, info, result, changed

    def _mirror(self, now, info):
        """Ghi 'bộ điều khiển đang nghĩ gì' lên twin. Lỗi ở đây không chặn vòng lặp."""
        if not self.push:
            return
        try:
            self.push(POOL_ID, {'controller': {'properties': {
                'mode': 'HOLD' if info['code'].startswith('hold') else 'ACTIVE',
                'code': info['code'], 'rho': info.get('rho'), 'target': info.get('target'),
                'loadLevel': info.get('load'), 'failoverLevel': info.get('failover'),
                'dryRun': bool(getattr(self.actuator, 'dry_run', False)),
                'tDecision': now}}})
        except Exception:  # noqa: BLE001
            pass

    def run(self, max_cycles=None):
        print('🧠 cloud controller: nhịp %.1fs, đọc %s + %s + %s%s' % (
            self.p.period_s, SRV1_ID, LINK_ID, POOL_ID,
            '  (DRY-RUN: không gọi AWS)' if getattr(self.actuator, 'dry_run', False) else ''))
        next_t, n = time.monotonic(), 0
        try:
            while True:
                obs, info, result, changed = self.step()
                if changed:
                    print(format_line(self.wall(), obs, info, result))
                n += 1
                if max_cycles is not None and n >= max_cycles:
                    return
                next_t += self.p.period_s
                time.sleep(max(0.0, next_t - time.monotonic()))
        except KeyboardInterrupt:
            print('\n⏹  dừng controller.')


def _f(x, fmt):
    return '?' if x is None else fmt % x


def format_line(now, o, info, result):
    head = '%s  srv1=%s ρ=%s age=%ss | cloud desired=%s healthy=%s age=%ss' % (
        time.strftime('%H:%M:%S', time.localtime(now)), o.srv1_state,
        _f(info.get('rho'), '%.2f'), _f(o.net_age_s, '%.1f'),
        _f(o.cloud_desired, '%d'), _f(o.cloud_healthy, '%d'), _f(o.cloud_age_s, '%.1f'))
    if info['code'].startswith('hold'):
        return '%s  ⏸  %s' % (head, info['code'])
    tail = '  → target=%d [load=%d failover=%d %s]' % (
        info['target'], info['load'], info['failover'], info['code'])
    if result is not None:
        tail += '  ⇒ set_capacity %s' % result['outcome']
    return head + tail


# ===========================================================================
def main(argv=None):
    p = argparse.ArgumentParser(description='Bộ điều khiển cloud (GĐ1.4)')
    sub = p.add_subparsers(dest='cmd', required=True)
    o = sub.add_parser('once')
    r = sub.add_parser('run')
    r.add_argument('--period', type=float, default=Params.period_s)
    for x in (o, r):
        x.add_argument('--dry-run', action='store_true')
    a = p.parse_args(argv)

    from bridge.ditto_reader import make_session
    from cloud.actuator import CloudActuator
    session = make_session()
    params = Params(period_s=getattr(a, 'period', Params.period_s))
    ctl = CloudController(CloudActuator(dry_run=a.dry_run), lambda: observe(session), params)
    if a.cmd == 'once':
        obs, info, result, _ = ctl.step()
        print(json.dumps({'obs': asdict(obs), 'info': info,
                          'action': result}, indent=2, ensure_ascii=False))
    else:
        ctl.run()


if __name__ == '__main__':
    sys.exit(main())
