#!/usr/bin/env python3
"""
whatif/blind.py — GĐ3.5: KIỂM MÙ mô hình what-if trên testbed sống.

VÌ SAO CẦN: 3.2 là kiểm hồi cứu (số đo đã có, đã thấy trước). Kiểm mù = viết dự đoán ra,
COMMIT nó (git ghi thời điểm), RỒI mới gây sự cố và đo. Dự đoán không thể bị "chỉnh cho khớp".
Ca 2 còn kiểm có tiên lượng công thức thời gian đầy hàng đợi B/(λ−C) mà 3.2 mới chỉ tìm ra
HẬU NGHIỆM: một phát hiện hậu nghiệm chỉ thành bằng chứng khi đứng được trên dữ liệu mới.

HAI CA CHƯA TỪNG CHẠY Ở PHASE 5 (cả hai trong vùng hợp lệ: chỉ UDP qua link nghẽn)
  case1  flood UDP srv2 -> srv1 8 Mbps: đi NGƯỢC qua nút cổ chai (chiều s3->s2, 5 Mbps)
  case2  setBandwidth s2-s3 = 1,5 Mbps (Phase 5 chỉ có mức 1,0): luồng nền 2,16 Mbps bị nghẽn
         nhẹ -> hàng đợi đầy CHẬM (~18 s) -> kiểm được thời điểm bắt đầu mất gói

QUY TRÌNH (thứ tự được code ÉP, không chỉ dặn):
  1. predict  đọc twin lúc mạng bình thường -> ghi results/gd3/blind_predictions.json
              (kèm ngưỡng ĐẠT/TRƯỢT và cửa sổ chấm, cố định từ trước)
  2. git commit file dự đoán         (measure TỪ CHỐI chạy nếu file chưa commit hoặc bị sửa)
  3. measure case1   người vận hành gõ iperf ở mininet>; script lấy mẫu twin 1 Hz trong 70 s
  4. measure case2   script gửi setBandwidth qua hộp thư Ditto, lấy mẫu 70 s, rồi trả về 5 Mbps
  5. score    chấm từng dự đoán -> results/gd3/blind_result.json (không bao giờ ghi đè)

LƯU Ý: khác server/live (chỉ đọc), file NÀY có gửi lệnh (case2) — vì nó là THÍ NGHIỆM.

CÁCH CHẠY (cần Ditto + Mininet + sync đang chạy, mạng ở tải bình thường):
    python3 -m whatif.blind predict
    git add results/gd3/blind_predictions.json && git commit -m "GĐ3.5: dự đoán mù"
    python3 -m whatif.blind measure case1
    python3 -m whatif.blind measure case2
    python3 -m whatif.blind score
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

from ml import campaign as C
from whatif import live as L
from whatif import model as M
from whatif import validate as V

OUT_DIR = 'results/gd3'
PRED = OUT_DIR + '/blind_predictions.json'
SAMPLES = OUT_DIR + '/blind_samples_%s_try%d.jsonl'
RESULT = OUT_DIR + '/blind_result.json'
MEASURE_S = 70
SETTLE_S = 5            # chấm trạng thái ổn định từ (thời gian đầy dự đoán + 5 s)
STEADY_END_S = 55       # ... tới giây 55 (flood chạy 60 s)
TOL = {'rate_abs_mbps': 0.25, 'rate_rel': 0.05, 'loss_pp': 3.0, 'time_s': 3.0}
BG_NOMINAL = 2.0

CASES = {
    'case1': {'title': 'flood UDP srv2 -> srv1 8 Mbps (ngược qua nút cổ chai s3->s2)',
              'action': {'op': 'addDemand', 'src': 'srv2', 'dst': 'srv1', 'kind': 'udp'},
              'nominal_mbps': 8.0,
              'operator': ['srv1 iperf -s -u -p 5099 > /tmp/blind_srv1.log 2>&1 &',
                           'srv2 iperf -c 10.0.0.4 -u -b 8M -p 5099 -t 60 &'],
              'hot': ('s3', 's2'), 'down_stream': ('s2', 'srv1'),
              'controls': [('s1', 's3'), ('s2', 's3')], 'score_time': False},
    'case2': {'title': 'setBandwidth s2-s3 = 1,5 Mbps (mức chưa từng chạy)',
              'action': {'op': 'setBandwidth', 'link': 's2-s3', 'mbps': 1.5},
              'restore_mbps': 5.0,
              'hot': ('s2', 's3'), 'down_stream': ('s3', 'srv2'),
              'controls': [('s1', 's2')], 'score_time': True},
}


def _git(*args) -> str:
    return subprocess.run(['git', *args], cwd=C.ROOT, capture_output=True,
                          text=True).stdout.strip()


def link_loss_pct(pred: dict, key: str) -> float:
    """lossPct của collector gộp CẢ HAI chiều và đếm theo GÓI. Hai chiều ở đây đều là UDP cùng
    cỡ gói, nên tỉ lệ theo byte của (tổng bỏ / tổng đến) hai chiều = tỉ lệ theo gói."""
    a, b = key.split('-')
    dirs = [pred['links'].get('%s->%s' % (a, b)), pred['links'].get('%s->%s' % (b, a))]
    arrive = sum(d['load'] for d in dirs if d)
    dropped = sum(max(0.0, d['load'] - d['capacity']) for d in dirs if d)
    return 100.0 * dropped / arrive if arrive > 0 else 0.0


# ===========================================================================
# 1. DỰ ĐOÁN
# ===========================================================================
def make_predictions(read=None) -> dict:
    things, ages, meta = (read or L.read_twin)()
    state, report = L.state_from_things(things, ages)
    if not report['ok']:
        raise SystemExit('Twin chưa đủ tươi/đủ Thing -> không dự đoán: %s' % report['warnings'])
    bg = report['inputs_mbps']['srv1->srv2']
    k = bg / BG_NOMINAL                 # hệ số "danh nghĩa iperf -> trên dây" đo từ luồng nền
    cases = {}
    for name, spec in CASES.items():
        action = dict(spec['action'])
        if action['op'] == 'addDemand':
            action['mbps'] = spec['nominal_mbps'] * k
        pred = M.predict(M.apply(state, action))
        hot = pred['links']['%s->%s' % spec['hot']]
        key = hot['link']
        fill = V.fill_time_s(hot['load'], hot['capacity'])
        start = math.ceil((fill or 0) + SETTLE_S)
        items = [
            {'id': name[-1] + 'a', 'what': 'tải chiều %s->%s (Mbps)' % spec['hot'], 'kind': 'rate',
             'dlink': '%s->%s' % spec['hot'], 'pred': min(hot['load'], hot['capacity'])},
            {'id': name[-1] + 'b', 'what': 'lossPct link %s (%%, hai chiều)' % key, 'kind': 'loss',
             'link': key, 'pred': link_loss_pct(pred, key)},
            {'id': name[-1] + 'c', 'what': 'tải chiều %s->%s (Mbps)' % spec['down_stream'],
             'kind': 'rate', 'dlink': '%s->%s' % spec['down_stream'],
             'pred': pred['links']['%s->%s' % spec['down_stream']]['load']},
        ]
        if spec['score_time']:
            items.append({'id': name[-1] + 't', 'kind': 'time', 'link': key,
                          'what': 'giây tới lúc bắt đầu mất gói (lossPct > 1%)', 'pred': fill})
        for i, d in enumerate(spec['controls']):
            items.append({'id': '%sk%d' % (name[-1], i + 1), 'kind': 'rate', 'control': True,
                          'what': 'ĐỐI CHỨNG: chiều %s->%s không đổi (Mbps)' % d,
                          'dlink': '%s->%s' % d, 'pred': pred['links']['%s->%s' % d]['load']})
        cases[name] = {'title': spec['title'], 'action': action, 'fill_time_s': fill,
                       'steady_window_s': [start, STEADY_END_S],
                       'outside_validity': pred['summary']['outside_validity'],
                       'operator': spec.get('operator'), 'items': items}
    content = {
        'what': 'GĐ3.5 — dự đoán MÙ, viết trước khi gây sự cố',
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'git_head': _git('rev-parse', 'HEAD'),
        'inputs_from_twin': {'inputs_mbps': report['inputs_mbps'],
                             'max_age_s': report['max_age_s'], 'warnings': report['warnings']},
        'k_wire_over_nominal': k,
        'tolerances': TOL,
        'rules': ('ĐẠT nếu |dự đoán − đo| <= max(%.2f Mbps, %d%% dự đoán) với tải; <= %.0f điểm %% '
                  'với lossPct; <= %.0f s với thời điểm mất gói. Tải và lossPct lấy TRUNG BÌNH '
                  'mẫu twin trong cửa sổ ổn định của từng ca. Mỗi ca đo MỘT lần; lần đo hỏng '
                  '(twin không tươi, lệnh bị từ chối) được ghi lại và đo lại với --try 2, '
                  'không bỏ dự đoán nào.' % (TOL['rate_abs_mbps'], 100 * TOL['rate_rel'],
                                             TOL['loss_pp'], TOL['time_s'])),
        'cases': cases,
    }
    return {'content': content,
            'content_sha256': C.sha256_bytes(C.canonical_json(content).encode('utf-8'))}


# ===========================================================================
# 2. ĐO
# ===========================================================================
def is_committed_unchanged(rel: str) -> bool:
    tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', rel], cwd=C.ROOT,
                             capture_output=True).returncode == 0
    clean = subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', rel], cwd=C.ROOT,
                           capture_output=True).returncode == 0
    return tracked and clean


def send_command(subject: str, target: str, **params) -> int:
    """Gửi lệnh vào hộp thư Ditto của controller Thing — đúng đường của dashboard."""
    import requests
    from bridge.ditto_common import DITTO_AUTH, DITTO_BASE_URL, NAMESPACE
    url = '%s/things/%s:controller/inbox/messages/%s?timeout=0' % (
        DITTO_BASE_URL, NAMESPACE, subject)
    r = requests.post(url, json=dict(params, target=target), auth=DITTO_AUTH, timeout=5,
                      headers={'correlation-id': 'gd35-' + uuid.uuid4().hex[:12]})
    return r.status_code


def sample_row(t0: float, read=None) -> dict:
    things, ages, _ = (read or L.read_twin)()
    links = {}
    for name, t in things.items():
        if name.startswith('link-'):
            tr = t['features'].get('traffic') or {}
            links[name[5:]] = {k: tr.get(k) for k in ('txRate', 'rxRate', 'lossPct', 'utilIntf',
                                                       'rateValid', 'qdiscValid')}
    known = [a for a in ages.values() if a is not None]
    return {'t': time.time(), 'rel': time.time() - t0, 'max_age_s': max(known) if known else None,
            'links': links}


def measure(case: str, try_no: int = 1, read=None, sleep=time.sleep) -> str:
    if not is_committed_unchanged(PRED):
        raise SystemExit('Commit %s TRƯỚC khi đo (dự đoán phải có trước dữ liệu).' % PRED)
    out = C.ROOT / (SAMPLES % (case, try_no))
    if out.exists():
        raise SystemExit('Đã có %s; lần đo lại dùng --try %d' % (out, try_no + 1))
    spec = CASES[case]
    events = []
    if case == 'case1':
        print('Gõ ở mininet> (đã gõ lệnh 1 từ trước thì bỏ qua):')
        for line in spec['operator']:
            print('    ' + line)
        input('Gõ sẵn lệnh 2 (CHƯA Enter). Bấm Enter Ở ĐÂY rồi NGAY LẬP TỨC Enter ở mininet> ')
        t0 = time.time()
        events.append({'kind': 'inject_manual', 't': t0})
    else:
        target = L.thing_ids()['link-' + spec['action']['link']]
        code = send_command('setBandwidth', target, bw=spec['action']['mbps'])
        t0 = time.time()
        events.append({'kind': 'inject_command', 't': t0, 'http_status': code})
        if code >= 300:
            raise SystemExit('Lệnh setBandwidth bị từ chối: HTTP %d' % code)
    rows = []
    try:
        for i in range(MEASURE_S):
            rows.append(sample_row(t0, read))
            sleep(max(0.0, t0 + i + 1 - time.time()))
    finally:
        if case == 'case2':
            code = send_command('setBandwidth', target, bw=spec['restore_mbps'])
            events.append({'kind': 'restore_command', 't': time.time(), 'http_status': code})
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps({'header': True, 'case': case, 'try': try_no, 'events': events,
                                 'predictions_sha256': json.loads(
                                     (C.ROOT / PRED).read_text())['content_sha256']},
                                ensure_ascii=False) + '\n')
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    return str(out)


# ===========================================================================
# 3. CHẤM
# ===========================================================================
def _directed(row: dict, dlink: str):
    a, b = dlink.split('->')
    rec = row['links'].get(M.canonical(a, b))
    if not rec or rec.get('rateValid') is False or not rec.get('utilIntf'):
        return None
    owner = rec['utilIntf'].split('-')[0]
    v = rec.get('txRate') if owner == a else rec.get('rxRate')
    return None if not isinstance(v, (int, float)) else v * 8e-6


def score_case(case: dict, rows: list) -> list:
    lo, hi = case['steady_window_s']
    steady = [r for r in rows if lo <= r['rel'] <= hi]
    out = []
    for it in case['items']:
        if it['kind'] == 'rate':
            meas = V._mean([_directed(r, it['dlink']) for r in steady])
            tol = max(TOL['rate_abs_mbps'], TOL['rate_rel'] * it['pred'])
        elif it['kind'] == 'loss':
            meas = V._mean([(r['links'].get(it['link']) or {}).get('lossPct') for r in steady
                            if (r['links'].get(it['link']) or {}).get('qdiscValid') is not False])
            tol = TOL['loss_pp']
        else:
            first = next((r['rel'] for r in rows if r['rel'] > 0 and isinstance(
                (r['links'].get(it['link']) or {}).get('lossPct'), (int, float))
                and r['links'][it['link']]['lossPct'] > 1.0), None)
            meas, tol = first, TOL['time_s']
        ok = meas is not None and abs(it['pred'] - meas) <= tol
        out.append(dict(it, meas=meas, tol=tol, n=len(steady), verdict='ĐẠT' if ok else 'TRƯỢT'))
    return out


def score(tries=None) -> dict:
    pred = json.loads((C.ROOT / PRED).read_text(encoding='utf-8'))
    result = {'what': 'GĐ3.5 — chấm dự đoán mù', 'predictions_sha256': pred['content_sha256'],
              'predictions_commit': _git('log', '-1', '--format=%H %cI', '--', PRED),
              'cases': {}}
    for name, case in pred['content']['cases'].items():
        try_no = (tries or {}).get(name, 1)
        path = C.ROOT / (SAMPLES % (name, try_no))
        lines = path.read_text(encoding='utf-8').splitlines()
        header, rows = json.loads(lines[0]), [json.loads(x) for x in lines[1:]]
        if header['predictions_sha256'] != pred['content_sha256']:
            raise SystemExit('%s đo với một bản dự đoán khác' % path)
        result['cases'][name] = {'title': case['title'], 'try': try_no,
                                 'events': header['events'], 'items': score_case(case, rows)}
    items = [i for c in result['cases'].values() for i in c['items']]
    result['summary'] = {'n': len(items), 'pass': sum(i['verdict'] == 'ĐẠT' for i in items)}
    return result


def _write_once(rel: str, doc) -> None:
    path = C.ROOT / rel
    if path.exists():
        raise SystemExit('Đã tồn tại, không ghi đè: %s' % rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    C.atomic_json(path, doc)


def print_predictions(doc: dict) -> None:
    c = doc['content']
    print('k (trên dây / danh nghĩa) = %.3f; tuổi twin lớn nhất %.1f s' % (
        c['k_wire_over_nominal'], c['inputs_from_twin']['max_age_s'] or 0))
    for name, case in c['cases'].items():
        print('\n%s — %s' % (name, case['title']))
        print('   cửa sổ chấm ổn định: giây %d..%d; ngoài vùng hợp lệ: %s' % (
            case['steady_window_s'][0], case['steady_window_s'][1],
            case['outside_validity'] or 'không có'))
        for it in case['items']:
            print('   %-4s %-46s dự đoán %7.2f' % (it['id'], it['what'], it['pred']))


def print_result(res: dict) -> None:
    for name, case in res['cases'].items():
        print('\n%s — %s (lần đo %d)' % (name, case['title'], case['try']))
        for it in case['items']:
            meas = '   –  ' if it['meas'] is None else '%7.2f' % it['meas']
            print('   %-4s %-46s dự đoán %7.2f  đo %s  (±%.2f)  %s' % (
                it['id'], it['what'], it['pred'], meas, it['tol'], it['verdict']))
    s = res['summary']
    print('\nTỔNG: %d/%d dự đoán ĐẠT' % (s['pass'], s['n']))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m whatif.blind')
    ap.add_argument('cmd', choices=['predict', 'measure', 'score'])
    ap.add_argument('case', nargs='?', choices=sorted(CASES))
    ap.add_argument('--try', dest='try_no', type=int, default=1)
    ns = ap.parse_args(argv)
    if ns.cmd == 'predict':
        doc = make_predictions()
        _write_once(PRED, doc)
        print_predictions(doc)
        print('\n✅ đã ghi %s — COMMIT nó trước khi đo.' % PRED)
    elif ns.cmd == 'measure':
        if not ns.case:
            ap.error('measure cần case1 hoặc case2')
        print('✅ đã ghi %s' % measure(ns.case, ns.try_no))
    else:
        res = score()
        _write_once(RESULT, res)
        print_result(res)
        print('\nđã ghi %s' % RESULT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
