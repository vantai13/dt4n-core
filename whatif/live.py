#!/usr/bin/env python3
"""
whatif/live.py — GĐ3.3: hỏi what-if từ trạng thái HIỆN TẠI của twin.

LUỒNG
  Ditto (5 host + 8 link Thing) --đọc 1 lần--> dựng State (dung lượng, link tắt, nhu cầu)
  --> áp hành động --> predict --> so với "không làm gì".  KHÔNG gửi lệnh nào xuống mạng.

ĐỌC GÌ TỪ TWIN
  link-*        status.state (up/down), capacity.bwMbps (băng thông ĐANG đặt),
                traffic.txRate/rxRate + utilIntf (biết chiều nào là chiều nào), rateValid
  host-h1..h3   traffic.txRate -> nhu cầu client; đích lấy từ cấu hình (GIẢ ĐỊNH, như 3.1)
  link-s2-s3    chiều s2->s3 -> luồng nền srv1->srv2 (dự phòng: txRate của srv1)
  meta.tSource  -> tuổi của từng Thing

BA CÁI BẪY CỦA TWIN (bài P2) VÀ CÁCH XỬ LÝ
  1. Merge-patch giữ số cũ: khi rateValid=false, adapter bỏ txRate (None không được gửi)
     nên twin còn số CŨ. -> rate có rateValid=false bị bỏ, dùng mức danh nghĩa + cảnh báo.
  2. Twin chỉ nhận delta, đủ trạng thái mỗi ~30 s -> tSource có thể cũ tới ~30 s dù mạng
     vẫn sống. -> Thing nào cũ hơn MAX_AGE_S = 45 s thì TỪ CHỐI trả lời (trừ --allow-stale).
  3. Twin đo tốc độ ĐANG GỬI, không phải tốc độ MUỐN GỬI: khi mạng đang nghẽn, TCP đã lùi,
     nên "nhu cầu" đọc được thấp hơn nhu cầu thật. -> nếu đang có link ρ >= 0,95 thì cảnh
     báo: dự đoán sau khi gỡ nghẽn sẽ đánh giá THẤP tải của các luồng đã lùi.
  Thêm: twin không biết giao thức. Client gửi gấp nhiều lần mức cấu hình (đang flood) vẫn
  bị coi là TCP -> cảnh báo, và cờ vùng hợp lệ của client đó không đáng tin.

CÁCH CHẠY
    python3 -m whatif.live now                                  # cần Ditto đang chạy
    python3 -m whatif.live ask --disable s1-s2
    python3 -m whatif.live ask --set-bw h1-s1=7 --flood h1:srv1:50
    python3 -m whatif.live ask --snapshot F-flood-h1_to_srv1-s3005-r1:30 --set-bw h1-s1=7
        (--snapshot RUN:TICK đọc một snapshot Phase 5 thay cho Ditto: thử không cần mạng)
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from ml import campaign as C
from whatif import model as M

MAX_AGE_S = 45.0
CONGESTED_RHO = 0.95
OVER_NOMINAL = 1.5
NOMINAL = {d.src: d.mbps for d in M.NORMAL_DEMANDS}
CLIENT_DST = {d.src: d.dst for d in M.NORMAL_DEMANDS if d.kind == 'tcp'}
BG = ('srv1', 'srv2')


# ===========================================================================
# ĐỌC: twin (Ditto) hoặc snapshot Phase 5 -> cùng một dạng "phẳng"
#   {'host-h1': {'attributes': {...}, 'features': {'traffic': {...}}}, ...}, tuổi {tên: giây}
# ===========================================================================
def _flat(body: dict) -> dict:
    """Bỏ tầng 'properties' của Ditto để twin và snapshot có cùng dạng."""
    feats = {}
    for name, feat in (body.get('features') or {}).items():
        feats[name] = feat.get('properties', feat) if isinstance(feat, dict) else {}
    return {'attributes': body.get('attributes') or {}, 'features': feats}


def thing_ids(spec=None) -> dict:
    from bridge.ditto_common import make_thing_id_host, make_thing_id_link
    spec = spec or M.load_spec()
    ids = {'host-' + h['name']: make_thing_id_host(h['name']) for h in spec['hosts']}
    for a, b in spec['links']:
        ids['link-' + M.canonical(a, b)] = make_thing_id_link(a, b)
    return ids


def read_twin(session=None, spec=None):
    from bridge.ditto_reader import extract_t_source, fetch_all_things, make_session
    session = session or make_session()
    ids = thing_ids(spec)
    bodies, meta = fetch_all_things(session, list(ids.values()))
    things, ages = {}, {}
    for short, tid in ids.items():
        if tid not in bodies:
            continue
        things[short] = _flat(bodies[tid])
        t_src = extract_t_source(bodies[tid])
        ages[short] = None if t_src is None else meta['read_times'][tid] - t_src
    return things, ages, {'source': 'ditto', 'n_ok': meta['n_ok'], 'n_fail': meta['n_fail'],
                          'missing': sorted(set(ids) - set(things))}


def read_snapshot(run_id: str, tick: int):
    snaps = C.read_snapshots(C.run_paths(run_id)['final'])
    snap = next(s for s in snaps if s['tick'] == tick)
    things = {k: _flat(v) for k, v in snap['things'].items()
              if k.startswith(('host-', 'link-'))}
    ages = {k: max(0.0, snap['t_source'] - v['t_source']) for k, v in snap['things'].items()
            if k in things and v.get('t_source') is not None}
    return things, ages, {'source': 'snapshot %s tick %d' % (run_id, tick), 'missing': []}


# ===========================================================================
# DỰNG STATE TỪ TRẠNG THÁI ĐỌC ĐƯỢC
# ===========================================================================
def _rate_mbps(traffic: dict, key: str):
    v = traffic.get(key)
    if traffic.get('rateValid') is False or isinstance(v, bool) or \
            not isinstance(v, (int, float)):
        return None
    return v * 8e-6


def state_from_things(things: dict, ages: dict, spec=None, max_age=MAX_AGE_S,
                      restore_nominal=False):
    """restore_nominal=True: client nào đang gửi DƯỚI mức cấu hình thì nâng lên mức cấu hình
    (GIẢ ĐỊNH: luồng TCP đã lùi sẽ quay lại khi hết nghẽn). Dùng khi hỏi "gỡ nghẽn thì sao"."""
    spec = spec or M.load_spec()
    base = M.default_state(spec=spec, demands=[])
    warnings, inputs, restored = [], {}, {}

    stale = sorted(k for k, a in ages.items() if a is not None and a > max_age)
    no_age = sorted(k for k in things if ages.get(k) is None)
    missing = sorted(k for k in thing_ids(spec) if k not in things)
    if stale:
        warnings.append('Thing quá cũ (> %.0f s): %s' % (max_age, ', '.join(stale)))
    if missing:
        warnings.append('không đọc được: %s' % ', '.join(missing))

    capacity, down = dict(base.capacity), set()
    for key in base.capacity:
        t = things.get('link-' + key)
        if not t:
            continue
        bw = (t['features'].get('capacity') or {}).get('bwMbps')
        if isinstance(bw, (int, float)) and bw > 0:
            capacity[key] = float(bw)
        if (t['features'].get('status') or {}).get('state') == 'down':
            down.add(key)

    demands = []
    for client, dst in CLIENT_DST.items():
        traffic = (things.get('host-' + client) or {}).get('features', {}).get('traffic') or {}
        rate = _rate_mbps(traffic, 'txRate')
        if rate is None:
            rate = NOMINAL[client]
            warnings.append('%s không có txRate hợp lệ -> dùng mức danh nghĩa %.1f Mbps'
                            % (client, rate))
        elif rate > OVER_NOMINAL * NOMINAL[client]:
            warnings.append('%s đang gửi %.2f Mbps, gấp %.1f lần mức cấu hình: twin không biết '
                            'giao thức, cờ vùng hợp lệ của %s không đáng tin'
                            % (client, rate, rate / NOMINAL[client], client))
        if restore_nominal and rate < NOMINAL[client]:
            restored[client] = rate
            warnings.append('đã nâng %s từ %.2f lên mức cấu hình %.1f Mbps (giả định: luồng đã '
                            'lùi sẽ quay lại khi hết nghẽn)' % (client, rate, NOMINAL[client]))
            rate = NOMINAL[client]
        inputs['%s->%s' % (client, dst)] = rate
        if rate > 0:
            demands.append(M.Demand(client, dst, rate, 'tcp'))

    bg = None
    link23 = things.get('link-s2-s3')
    if link23 and 's2-s3' not in down:
        traffic = link23['features'].get('traffic') or {}
        owner = str(traffic.get('utilIntf', '')).split('-')[0]
        bg = _rate_mbps(traffic, 'txRate' if owner == 's2' else 'rxRate') if owner else None
    if bg is None:
        traffic = (things.get('host-srv1') or {}).get('features', {}).get('traffic') or {}
        bg = _rate_mbps(traffic, 'txRate')
        warnings.append('luồng nền đo bằng txRate của srv1 (gồm cả ACK, hơi cao)')
    if bg is None:
        bg = NOMINAL['srv1']
        warnings.append('luồng nền không có số đo -> dùng danh nghĩa %.1f Mbps' % bg)
    inputs['%s->%s' % BG] = bg
    if bg > 0:
        demands.append(M.Demand(BG[0], BG[1], bg, 'udp'))

    state = M.State(spec=spec, capacity=capacity, down=down, demands=demands)
    now = M.predict(state)
    if now['summary']['max_rho'] >= CONGESTED_RHO and not restore_nominal:
        warnings.append('đang có link gần/đang nghẽn (%s ρ=%.2f): tốc độ đọc được có thể THẤP hơn '
                        'nhu cầu thật (TCP đã lùi) -> dự đoán sau khi gỡ nghẽn đánh giá thấp '
                        'tải của các luồng đã lùi; thử thêm --restore-nominal'
                        % (now['summary']['hottest'], now['summary']['max_rho']))
    known = [a for a in ages.values() if a is not None]
    report = {'inputs_mbps': inputs, 'restored_from': restored, 'down': sorted(down),
              'capacity_changed': {k: v for k, v in capacity.items()
                                   if abs(v - base.capacity[k]) > 1e-9},
              'max_age_s': max(known) if known else None, 'stale': stale,
              'no_age': no_age, 'missing': missing, 'warnings': warnings,
              'ok': not stale and not missing}
    return state, report


# ===========================================================================
# HỎI
# ===========================================================================
def ask(state: M.State, actions: list, label='hành động') -> dict:
    return M.compare(state, {label: actions} if actions else {})


def parse_actions(ns) -> list:
    actions = []
    for link in ns.disable or []:
        actions.append({'op': 'disableLink', 'link': link})
    for link in ns.enable or []:
        actions.append({'op': 'enableLink', 'link': link})
    for item in ns.set_bw or []:
        link, mbps = item.split('=')
        actions.append({'op': 'setBandwidth', 'link': link, 'mbps': float(mbps)})
    for item in ns.flood or []:
        src, dst, mbps = item.split(':')
        actions.append({'op': 'addDemand', 'src': src, 'dst': dst, 'mbps': float(mbps),
                        'kind': 'udp'})
    return actions


def _short(name: str) -> str:
    return name.replace('->', '→').split('/')[0]


def print_answer(report: dict, result: dict) -> None:
    print('Đầu vào (%s, tuổi lớn nhất %s):' % (
        report.get('source', '?'),
        '-' if report['max_age_s'] is None else '%.1f s' % report['max_age_s']))
    print('  nhu cầu (Mbps): ' + '  '.join('%s %.2f' % (k.replace('->', '→'), v)
                                          for k, v in report['inputs_mbps'].items()))
    print('  link tắt: %s   băng thông khác mặc định: %s' % (
        ', '.join(report['down']) or '-',
        ', '.join('%s=%.2f' % kv for kv in report['capacity_changed'].items()) or '-'))
    for w in report['warnings']:
        print('  ⚠ ' + w)
    print()
    for label, r in result.items():
        p = r['prediction']
        hot = sorted(((k, v['rho']) for k, v in p['links'].items() if v['rho'] >= 0.9),
                     key=lambda kv: -kv[1])
        print('[%s] %s' % (label, ' + '.join(json.dumps(a, ensure_ascii=False)
                                            for a in r['actions']) or ''))
        print('   link nóng (ρ ≥ 0.9): %s' % (' '.join('%s=%.2f' % kv for kv in hot) or '-'))
        print('   luồng tới đích (Mbps): ' + '  '.join(
            '%s %.2f' % (_short(n), f['delivered']) for n, f in p['flows'].items()))
        if p['summary']['unreachable']:
            print('   không tới được: %s' % ', '.join(p['summary']['unreachable']))
        print('   nạn nhân mới: %s   ngoài vùng hợp lệ: %s' % (
            ', '.join(map(_short, r['new_victims'])) or '-',
            ', '.join(map(_short, p['summary']['outside_validity'])) or '-'))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m whatif.live')
    ap.add_argument('cmd', choices=['now', 'ask'])
    ap.add_argument('--disable', action='append', metavar='LINK')
    ap.add_argument('--enable', action='append', metavar='LINK')
    ap.add_argument('--set-bw', action='append', metavar='LINK=MBPS')
    ap.add_argument('--flood', action='append', metavar='SRC:DST:MBPS')
    ap.add_argument('--snapshot', metavar='RUN_ID:TICK')
    ap.add_argument('--restore-nominal', action='store_true',
                    help='client đang gửi dưới mức cấu hình -> coi như sẽ quay lại mức cấu hình')
    ap.add_argument('--allow-stale', action='store_true')
    ap.add_argument('--json', action='store_true')
    ns = ap.parse_args(argv)

    if ns.snapshot:
        rid, tick = ns.snapshot.rsplit(':', 1)
        things, ages, meta = read_snapshot(rid, int(tick))
    else:
        things, ages, meta = read_twin()
    if not things:
        print('Không đọc được Thing nào từ Ditto. Ditto có đang chạy không '
              '(cd ditto && docker compose ps)? Đã bootstrap Thing chưa?')
        return 3
    state, report = state_from_things(things, ages, restore_nominal=ns.restore_nominal)
    report['source'] = meta['source']
    report['t_asked'] = time.time()
    if not report['ok'] and not ns.allow_stale:
        print('TỪ CHỐI trả lời: dữ liệu twin không đủ tươi/đủ Thing.')
        for w in report['warnings']:
            print('  ⚠ ' + w)
        print('Kiểm Ditto, collector và sync agent; hoặc thêm --allow-stale nếu chấp nhận rủi ro.')
        return 3
    actions = parse_actions(ns) if ns.cmd == 'ask' else []
    if ns.cmd == 'ask' and not actions:
        ap.error('ask cần ít nhất một hành động (--disable/--enable/--set-bw/--flood)')
    result = ask(state, actions)
    if ns.json:
        print(json.dumps({'report': report, 'result': result}, ensure_ascii=False,
                         default=list))
    else:
        print_answer(report, result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
