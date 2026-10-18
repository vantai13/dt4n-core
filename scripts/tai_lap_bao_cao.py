#!/usr/bin/env python3
"""
tai_lap_bao_cao.py — Tính lại mọi con số offline của báo cáo và so với kết quả đã lưu.

Không cần Mininet, Ditto hay AWS. Mỗi mục chạy lại đúng code đã tạo ra kết quả, trên dữ liệu
thô có trong repo, rồi so KHỚP TUYỆT ĐỐI với tệp kết quả trong results/report/. Không ghi đè
tệp nào.

Các phép đo cần testbed (độ trễ đồng bộ và lệnh, AWS, vòng kín) không tính lại ở đây được;
cách chạy chúng ở ket-qua-bao-cao/README.md.

Cách chạy (từ gốc repo, môi trường phân tích .venv, xem README):
    .venv/bin/python scripts/tai_lap_bao_cao.py            # mọi mục
    .venv/bin/python scripts/tai_lap_bao_cao.py --muc 5.3  # chỉ các mục bắt đầu bằng 5.3
Mã thoát 0 khi mọi mục chạy được đều KHỚP.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from ml import campaign as C  # noqa: E402

REPORT = ROOT / 'results/report'
GD4R_RS = ('RS-soak2M-s5001-r1', 'RS-soak2M-s5003-r3')
RN_RETRY = 'RN-load8M-s5014-r2'


def content(name: str) -> dict:
    doc = json.loads((REPORT / name).read_text(encoding='utf-8'))
    return doc['content'] if 'content' in doc else doc


def diff(a, b, path='') -> list:
    """Khác biệt đầu tiên giữa hai cấu trúc JSON (tối đa vài dòng)."""
    a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
    out = []

    def walk(x, y, p):
        if len(out) >= 5:
            return
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                if k not in x or k not in y:
                    out.append('%s/%s: chỉ có ở một bên' % (p, k))
                else:
                    walk(x[k], y[k], '%s/%s' % (p, k))
        elif isinstance(x, list) and isinstance(y, list) and len(x) == len(y):
            for i, (u, v) in enumerate(zip(x, y)):
                walk(u, v, '%s[%d]' % (p, i))
        elif x != y:
            out.append('%s: %r != %r' % (p, x, y))

    walk(a, b, path)
    return out


# ------------------------------------------------------------------ các mục
def muc_hoc_lai():
    """5.3 / 3.4: học lại detector 2.1 cho ra đúng K, E, biên, R, vùng vận hành."""
    from ml import gd2_envelope as GE
    from ml import gd4_retrain as R
    res = GE.fit_and_evaluate('v21', ROOT, loader=R.load_raw)
    model = json.loads((ROOT / 'models/envelope-2.1.0.json').read_text())['content']
    problems = diff({'thresholds': {k: {'K': v['K'], 'E': v['E']} for k, v in res['thresholds'].items()},
                     'bounds': res['bounds'], 'link_stats': res['link_stats']},
                    {'thresholds': model['thresholds'], 'bounds': model['bounds'],
                     'link_stats': model['link_stats']})
    train_raw, _, warmup, _ = R.load_raw('v21', ROOT)
    cal = R.conservation_calibration(train_raw, warmup)
    stored = content('gd4_conservation.json')['calibration']
    problems += diff({'R': cal['R'], 'owner': cal['owner']}, {'R': stored['R'], 'owner': stored['owner']})
    op = R.operating_numbers(R.train_paths(ROOT))
    st = content('gd4_retrain.json')['operating_range']['v21_train']
    problems += diff({k: op[k] for k in ('operating_range_T_mbps', 'client_tx_ceiling_mbps')},
                     {k: st[k] for k in ('operating_range_T_mbps', 'client_tx_ceiling_mbps')})
    return problems, 'K %d, E %.4f, R %.4f' % (res['thresholds']['rate_shared']['K'],
                                               res['thresholds']['primary']['E'], cal['R'])


def muc_tap_phat_trien():
    """5.3.1: excess, dual, vị trí báo nhầm, Isolation Forest trên tập phát triển."""
    from gd4_devset import envelope_part, iforest_part
    stored = content('gd4_devset.json')
    env, iff = envelope_part(), iforest_part()
    e = env['v21']
    return (diff(env, stored['envelope']) + diff(iff, stored['iforest']),
            'excess %d/160, %d/430; dual %d/160, %d/430; IF recall %.4f' % (
                e['secondary_excess']['tp'], e['secondary_excess']['fp'],
                e['secondary_dual']['tp'], e['secondary_dual']['fp'], iff['v21']['recall_mean']))


def _score(groups, runs=None, release='models/detector-release-2.1.0.json', set_name='gd4r',
           raw_dir=None):
    from gd4_score import score, verdicts
    result = score(ROOT / release, set_name, raw_dir, tuple(groups),
                   tuple(runs) if runs else None)
    return result, verdicts(result)


def muc_giam_bang_thong_va_flood():
    """5.3.2: S1, S4 (10 run giảm băng thông), flood và dịch nút cổ chai (4 run)."""
    _, v = _score(('RD', 'RC'))
    st = content('gd4_acceptance_v21.json')['verdicts']
    keys = ('S1', 'S4', 'RC_descriptive')
    return diff({k: v[k] for k in keys}, {k: st[k] for k in keys}), \
        'S1 %s, lớn nhất %.1f s, R-C %d/4' % (
            v['S1']['value'], v['S4']['value_ms'] / 1000,
            v['RC_descriptive']['envelope_only']['ttd']['n_detected'])


def muc_tai_cao():
    """5.3.2: tải cao 6-10 Mbps, chưa áp và đã áp bộ chặn vùng tải (6 run, s5014 lần 2)."""
    _, v = _score(('RN',))
    first = content('gd4_acceptance_v21.json')['verdicts']
    retry = content('gd4_acceptance_v21_rn_retry.json')['verdicts']
    problems = []
    for rid, row in v['S10']['envelope_only'].items():
        ref = retry if rid == RN_RETRY else first
        problems += diff(row, ref['S10']['envelope_only'][rid], rid)
        problems += diff(v['operational_guard']['per_run'][rid],
                         ref['operational_guard']['per_run'][rid], rid + '/guard')
    pub = sum(g['envelope_only']['published_alarm_ticks']
              for g in v['operational_guard']['per_run'].values())
    return problems, '6 run, giây còn báo động khi áp bộ chặn: %d' % pub


def muc_chay_nen():
    """5.3.2: báo động sai khi chạy nền, 2 run x 60 phút."""
    _, v = _score(('RS',), runs=GD4R_RS)
    st = content('gd4_acceptance_v21_rs.json')['verdicts']
    return diff(v['S2'], st['S2']), 'cận trên %.2f lần/giờ trên %.2f giờ' % (
        v['S2']['value'], v['S2']['exposure_hours'])


def muc_what_if():
    """5.4: kiểm hồi cứu what-if trên 10 run tập phát triển."""
    from whatif.validate import validate
    rep = validate(ROOT)
    st = content('gd3_whatif_validation.json')
    keys = ('summary_rates_mbps', 'summary_loss_pp')
    return diff({k: rep[k] for k in keys}, {k: st[k] for k in keys}), \
        'trong vùng: trung vị %.3f, lớn nhất %.2f Mbps' % (
            rep['summary_rates_mbps']['trong']['median_abs'],
            rep['summary_rates_mbps']['trong']['max_abs'])


def muc_s1s2():
    """5.3.3: excess và cột chỉ báo trên 5 run giảm băng thông s1-s2."""
    import gd4_s1s2_excess as S
    from ml.acceptance_guard import SnapshotReader
    from ml.release import DetectorRelease
    contract = json.loads((REPORT / 'gd4r_contract.json').read_text())
    manifest = json.loads((REPORT / 'gd4r_manifest.json').read_text())
    got = {}
    for name, path in S.RELEASES.items():
        release = DetectorRelease.load(ROOT / path)
        reader = SnapshotReader({k: v['sha256'] for k, v in manifest['runs'].items()})
        for record in S.runs(contract):
            rid = record['run_id']
            got.setdefault(rid, {})[name] = S.analyse(
                release, record, reader.read_once(rid, S.RAW / (rid + '.jsonl')))
    st = content('gd4_s1s2_excess.json')['runs']
    top = max(r['v21']['excess_max_21_39'] for r in got.values())
    return diff(got, st), 'excess lớn nhất giây 21-39: %.2f' % top


def muc_vong_kin_offline():
    """5.7: kiểm offline luật chọn ứng viên theo chiều trên dữ liệu có sẵn."""
    import gd4cl_offline_check as K
    from gd4cl_common import RELEASE_21, upper_bounds_bps
    from ml.release import DetectorRelease
    release = DetectorRelease.load(ROOT / RELEASE_21)
    upper = upper_bounds_bps(release)
    st = content('gd4cl_offline_check.json')['runs']
    got = {}
    for name, (contract_path, raw, keep) in K.SETS.items():
        contract = json.loads(Path(contract_path).read_text())
        for record in contract['runs']:
            path = raw / (record['run_id'] + '.jsonl')
            if keep(record) and path.exists():
                row = K.check_run(release, upper, path, K.culprit_of(record))
                row.update({'set': name, 'fault': record.get('fault'),
                            'target': record.get('fault_target'),
                            'culprit': K.culprit_of(record)})
                got[record['run_id']] = row
    return diff(got, st), '%d run' % len(got)


MUC = (
    ('3.4/5.3', 'Học lại detector 2.1 (K, E, biên, R, vùng vận hành)', muc_hoc_lai),
    ('5.3.1', 'Tập phát triển: excess, dual, Isolation Forest', muc_tap_phat_trien),
    ('5.3.2a', 'Tập kiểm tra độc lập: giảm băng thông, flood, dịch nút cổ chai', muc_giam_bang_thong_va_flood),
    ('5.3.2b', 'Tập kiểm tra độc lập: tải cao và bộ chặn vùng tải', muc_tai_cao),
    ('5.3.2c', 'Tập kiểm tra độc lập: chạy nền 2 giờ', muc_chay_nen),
    ('5.3.3', 'Link chỉ có TCP: excess trên 5 run s1-s2', muc_s1s2),
    ('5.4', 'What-if: kiểm hồi cứu', muc_what_if),
    ('5.7', 'Vòng kín: kiểm offline luật chọn ứng viên', muc_vong_kin_offline),
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--muc', help='chỉ chạy các mục có mã bắt đầu bằng chuỗi này')
    args = ap.parse_args(argv)
    rows, failed = [], 0
    for code, title, fn in MUC:
        if args.muc and not code.startswith(args.muc):
            continue
        t0 = time.monotonic()
        try:
            problems, note = fn()
            status = 'BỎ QUA' if problems is None else ('KHỚP' if not problems else 'LỆCH')
        except Exception as exc:          # in lỗi, chạy tiếp các mục khác
            problems, note, status = [repr(exc)], traceback.format_exc(limit=2), 'LỖI'
        failed += status in ('LỆCH', 'LỖI')
        rows.append((code, title, status, time.monotonic() - t0, note, problems or []))
        print('%-7s %-62s %-6s %5.0f s  %s' % (code, title, status, rows[-1][3],
                                              note.splitlines()[0] if note else ''), flush=True)
        for p in (problems or [])[:5] if status in ('LỆCH', 'LỖI') else []:
            print('        - %s' % p)
    print('\n%d mục, %d lệch hoặc lỗi.' % (len(rows), failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
