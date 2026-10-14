#!/usr/bin/env python3
"""
whatif/validate.py — GĐ3.2: đặt dự đoán what-if cạnh số đo THẬT của Phase 5.

CÂU HỎI: nếu đứng ở giây 19 của một run (mạng còn bình thường), biết sắp có sự cố X,
mô hình 3.1 có đoán đúng tải từng chiều link và mất gói trong lúc sự cố diễn ra không?

QUY TẮC (cố định trong code, áp cho MỌI run, không chọn ca):
  Run      : 10 run tập test Phase 5 (2 đối chứng C + 8 sự cố F). Không có tham số nào
             được "học", nên không cần tách train/test; dùng test vì có đủ loại sự cố.
  Đầu vào  : cửa sổ PRE = tick 5..19 (trước inject ở tick 20). Nhu cầu của h1, h2, h3 =
             trung bình txRate của chính host đó; luồng nền srv1->srv2 = trung bình chiều
             s2->s3 (lúc bình thường chỉ luồng nền đi chiều này). Đích của từng client lấy
             từ cấu hình traffic (GIẢ ĐỊNH, như 3.1).
  Hành động: dựng lại từ record.fault_parameters, đúng như kịch bản đã làm:
             admin_down -> disableLink; degrade -> setBandwidth max(1, C0·(1−factor))
             (công thức của rl/scenarios.LinkDegrade.apply); flood -> addDemand UDP;
             shift -> degrade + flood srv1->srv2 (gộp vào luồng nền: cùng đường, cùng UDP).
  Chấm     : cửa sổ EVAL = tick 25..39 (bỏ 5 tick quá độ sau inject, dừng trước revert 40).
             So từng CHIỀU link có dự đoán hoặc đo >= 0,5 Mbps (bỏ chiều chỉ có ACK).
             Dự đoán = tải mang được min(λ, C); đo = trung bình txRate/rxRate của link.
             Dùng TRUNG BÌNH chứ không dùng trung vị: trung bình của tổng = tổng các trung
             bình (cộng tải theo đường đi là phép cộng), trung vị thì không (bài P3).
  Vùng     : một chiều link là "ngoài vùng" nếu có luồng TCP bị gắn cờ outside_validity đi
             qua nó; còn lại là "trong vùng". Run có lịch tải đổi giữa PRE và EVAL (C-vary)
             phá giả định "nhu cầu đứng yên" -> báo riêng, không gộp vào tổng kết.
  Mất gói  : so ở link mà mô hình đoán có mất hoặc đo lossPct > 1%. Lưu ý: lossPct đo theo
             GÓI và gộp CẢ HAI chiều; mô hình tính theo BYTE của chiều nặng hơn.

TRUNG THỰC: đây là kiểm HỒI CỨU. Quy tắc viết trước khi chạy toàn bộ, nhưng khi khảo sát
dữ liệu mình đã thấy số của vài run (và bài P1 đã dạy các số này) -> không phải kiểm mù.
Kiểm mù là 3.5: viết dự đoán ra trước, rồi mới chạy.

CÁCH CHẠY (không cần Mininet; đọc dữ liệu Phase 5 có sẵn trong repo):
    python3 -m whatif.validate
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone

from ml import campaign as C
from whatif import model as M

PRE = (5, 19)
EVAL = (25, 39)
MIN_MBPS = 0.5
LOSS_MIN_PCT = 1.0
OUT = 'results/report/gd3_whatif_validation.json'
CLIENT_DST = {d.src: d.dst for d in M.NORMAL_DEMANDS if d.kind == 'tcp'}
BG = ('srv1', 'srv2')


# ===========================================================================
# ĐỌC SỐ ĐO
# ===========================================================================
def _window(snaps, window):
    lo, hi = window
    return [s for s in snaps if lo <= s['tick'] <= hi]


def _mean(values):
    values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return sum(values) / len(values) if values else None


def directed_rates(snaps, window) -> dict:
    """{'s1->s2': Mbps}. txRate đo ở utilIntf (chủ interface -> đầu kia), rxRate là chiều ngược."""
    out = {}
    rows = _window(snaps, window)
    for name, thing in rows[0]['things'].items():
        if not name.startswith('link-'):
            continue
        a, b = thing['attributes']['endpointA'], thing['attributes']['endpointB']
        owner = thing['features']['traffic']['utilIntf'].split('-')[0]
        other = b if owner == a else a
        tx, rx = [], []
        for s in rows:
            t = s['things'][name]['features'].get('traffic') or {}
            if t.get('rateValid') is False:
                continue
            tx.append(t.get('txRate'))
            rx.append(t.get('rxRate'))
        for key, vals in (('%s->%s' % (owner, other), tx), ('%s->%s' % (other, owner), rx)):
            mean = _mean(vals)
            out[key] = None if mean is None else mean * 8e-6
    return out


def host_tx(snaps, window) -> dict:
    out = {}
    for s_name in ('h1', 'h2', 'h3', 'srv1', 'srv2'):
        vals = []
        for s in _window(snaps, window):
            t = s['things']['host-' + s_name]['features']['traffic']
            if t.get('rateValid') is not False:
                vals.append(t.get('txRate'))
        mean = _mean(vals)
        out[s_name] = None if mean is None else mean * 8e-6
    return out


def link_loss(snaps, window) -> dict:
    out = {}
    rows = _window(snaps, window)
    for name in rows[0]['things']:
        if name.startswith('link-'):
            vals = [(s['things'][name]['features'].get('traffic') or {}).get('lossPct')
                    for s in rows
                    if (s['things'][name]['features'].get('traffic') or {}).get('qdiscValid')
                    is not False]
            out[name[5:]] = _mean(vals)
    return out


# ===========================================================================
# DỰNG ĐẦU VÀO + HÀNH ĐỘNG
# ===========================================================================
def applied_bw(params: dict) -> float:
    """Băng thông kịch bản degrade THỰC SỰ đặt (rl/scenarios.LinkDegrade.apply)."""
    return max(1.0, float(params['baseline']) * (1.0 - float(params['factor'])))


def input_state(snaps) -> M.State:
    tx = host_tx(snaps, PRE)
    bg = directed_rates(snaps, PRE)['%s->%s' % ('s2', 's3')]
    demands = [M.Demand(c, dst, tx[c], 'tcp') for c, dst in CLIENT_DST.items()]
    demands.append(M.Demand(BG[0], BG[1], bg, 'udp'))
    return M.default_state(demands=demands)


def fault_state(state: M.State, record: dict) -> tuple[M.State, list]:
    fault, p = record.get('fault'), record.get('fault_parameters') or {}
    actions = []
    if fault == 'admin_down':
        actions = [{'op': 'disableLink', 'link': p['link_key']}]
    elif fault in ('degrade', 'shift'):
        actions = [{'op': 'setBandwidth', 'link': p['link_key'], 'mbps': applied_bw(p)}]
    elif fault == 'flood':
        actions = [{'op': 'addDemand', 'src': p['src'], 'dst': p['dst'],
                    'mbps': float(p['rate_mbps']), 'kind': 'udp'}]
    elif fault is not None:
        raise ValueError('sự cố không biết: %s' % fault)
    state = M.apply_all(state, actions)
    if fault == 'shift':
        # flood srv1->srv2 cùng đường, cùng UDP với luồng nền -> gộp thành một luồng
        bg_name = '%s->%s/udp' % BG
        state.demands = [M.Demand(d.src, d.dst, d.mbps + float(p['rate_mbps']), d.kind)
                         if d.name == bg_name else d for d in state.demands]
        actions.append({'op': '(gộp vào luồng nền)', 'src': BG[0], 'dst': BG[1],
                        'mbps': float(p['rate_mbps'])})
    return state, actions


def demand_changes(record: dict) -> bool:
    """Lịch tải có đổi mức giữa PRE và EVAL không (giả định 'nhu cầu đứng yên' bị phá)."""
    sched = record.get('load_schedule')
    if not sched:
        return False
    def level_at(t):
        return [rate for start, rate in sched if start <= t][-1]
    levels = {level_at(t) for t in range(PRE[0], EVAL[1] + 1)}
    return len(levels) > 1


# ===========================================================================
# CHẤM MỘT RUN
# ===========================================================================
def check_run(record: dict, snaps: list) -> dict:
    state, actions = fault_state(input_state(snaps), record)
    pred = M.predict(state)
    measured = directed_rates(snaps, EVAL)
    flagged = set(pred['summary']['outside_validity'])
    broken = demand_changes(record)

    rates = []
    for d in sorted(set(pred['links']) | set(measured)):
        info = pred['links'].get(d)
        p_val = min(info['load'], info['capacity']) if info else 0.0
        m_val = measured.get(d)
        if m_val is None or max(p_val, m_val) < MIN_MBPS:
            continue
        outside = bool(info and set(info['flows']) & flagged)
        rates.append({'dlink': d, 'pred': p_val, 'meas': m_val, 'err': p_val - m_val,
                      'rel': abs(p_val - m_val) / max(m_val, MIN_MBPS),
                      'zone': 'giả định phá' if broken else ('ngoài' if outside else 'trong'),
                      'flows': info['flows'] if info else []})

    losses = []
    meas_loss = link_loss(snaps, EVAL)
    for key, m_val in sorted(meas_loss.items()):
        a, b = key.split('-')
        dirs = [pred['links'].get('%s->%s' % (a, b)), pred['links'].get('%s->%s' % (b, a))]
        dirs = [x for x in dirs if x]
        heavy = max(dirs, key=lambda x: x['load']) if dirs else None
        p_val = 100.0 * heavy['loss'] if heavy else 0.0
        if m_val is None or (p_val <= 0 and m_val <= LOSS_MIN_PCT):
            continue
        outside = bool(heavy and set(heavy['flows']) & flagged)
        losses.append({'link': key, 'pred_pct': p_val, 'meas_pct': m_val,
                       'err_pp': p_val - m_val,
                       'zone': 'giả định phá' if broken else ('ngoài' if outside else 'trong')})

    diagnostics = [diagnose_loss(record, snaps, r, pred) for r in losses
                   if r['zone'] == 'trong' and abs(r['err_pp']) > 5]
    return {'run_id': record['run_id'], 'fault': record.get('fault'),
            'target': record.get('fault_target'), 'actions': actions,
            'demand_changes': broken,
            'inputs_mbps': {d.name: d.mbps for d in state.demands},
            'outside_validity': sorted(flagged), 'rates': rates, 'losses': losses,
            'post_hoc_diagnostics': diagnostics}


# ===========================================================================
# CHẨN ĐOÁN HẬU NGHIỆM (thêm SAU khi thấy kết quả; KHÔNG đổi quy tắc chấm ở trên)
#   Mô hình 3.1 chỉ có TRẠNG THÁI ỔN ĐỊNH. Hàng đợi cần B/(λ − C) giây mới đầy (bài 1.3);
#   trước lúc đó chưa mất gói nào. Khi λ chỉ nhỉnh hơn C một chút, quá độ này dài.
#   Giả định: hàng đợi netem 1000 gói (giới hạn mặc định), gói 1512 byte (UDP iperf).
# ===========================================================================
QUEUE_PKTS = 1000
PKT_BYTES = 1512


def fill_time_s(load_mbps: float, cap_mbps: float) -> float | None:
    excess = load_mbps - cap_mbps
    return QUEUE_PKTS * PKT_BYTES * 8 / (excess * 1e6) if excess > 1e-9 else None


def diagnose_loss(record: dict, snaps: list, row: dict, pred: dict) -> dict:
    a, b = row['link'].split('-')
    dirs = [pred['links'].get('%s->%s' % (a, b)), pred['links'].get('%s->%s' % (b, a))]
    heavy = max((x for x in dirs if x), key=lambda x: x['load'])
    t_fill = fill_time_s(heavy['load'], heavy['capacity'])
    inject = record.get('t_inject') or EVAL[0]
    series = {s['tick']: (s['things']['link-' + row['link']]['features'].get('traffic') or {})
              .get('lossPct') for s in snaps if EVAL[0] - 5 <= s['tick'] <= EVAL[1]}
    first = next((t for t, v in sorted(series.items())
                  if t > inject and isinstance(v, (int, float)) and v > LOSS_MIN_PCT), None)
    after = [v for t, v in series.items()
             if first is not None and t >= first and isinstance(v, (int, float))]
    return {'link': row['link'], 'fill_time_s_pred': t_fill,
            'first_loss_tick_pred': None if t_fill is None else inject + t_fill,
            'first_loss_tick_meas': first,
            'loss_after_fill_meas_pct': _mean(after), 'loss_pred_pct': row['pred_pct'],
            'loss_series_pct': series}


def _summary(rows, key, rel=None):
    out = {}
    for zone in ('trong', 'ngoài', 'giả định phá'):
        sel = [r for r in rows if r['zone'] == zone]
        if not sel:
            continue
        errs = [abs(r[key]) for r in sel]
        out[zone] = {'n': len(sel), 'median_abs': statistics.median(errs), 'max_abs': max(errs)}
        if rel:
            out[zone]['median_rel'] = statistics.median(r[rel] for r in sel)
            out[zone]['share_rel_le_10pct'] = sum(r[rel] <= 0.10 for r in sel) / len(sel)
    return out


def validate(root=None) -> dict:
    root = root or C.ROOT
    contract = C.load_contract(root / 'results/report/experiment_matrix.json')
    records = {r['run_id']: r for r in contract['runs']}
    runs, inputs = [], {}
    for rid in contract['split']['test']:
        paths = C.run_paths(rid, root)
        side = json.loads(paths['meta'].read_text(encoding='utf-8'))
        sha = C.sha256_file(paths['final'])
        if sha != side['sha256']:
            raise ValueError('raw lệch sha256 sidecar: ' + rid)
        inputs[str(paths['final'].relative_to(root))] = sha
        runs.append(check_run(records[rid], C.read_snapshots(paths['final'])))
    rate_rows = [r for run in runs for r in run['rates']]
    loss_rows = [r for run in runs for r in run['losses']]
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True,
                          text=True).stdout.strip()
    return {
        'what': 'GĐ3.2 — kiểm hồi cứu what-if trên 10 run tập test Phase 5',
        'rules': {'pre_ticks': PRE, 'eval_ticks': EVAL, 'min_mbps': MIN_MBPS,
                  'loss_min_pct': LOSS_MIN_PCT, 'aggregate': 'mean'},
        'honesty_note': ('Kiểm hồi cứu: quy tắc cố định trước khi chạy toàn bộ, nhưng số của '
                         'vài run đã được thấy khi khảo sát dữ liệu và trong bài P1.'),
        'summary_rates_mbps': _summary(rate_rows, 'err', rel='rel'),
        'summary_loss_pp': _summary(loss_rows, 'err_pp'),
        'runs': runs,
        'provenance': {'git_head': head, 'inputs_sha256': inputs,
                       'code_sha256': {f: C.sha256_file(root / f) for f in
                                       ('whatif/model.py', 'whatif/validate.py')},
                       'generated_at_utc': datetime.now(timezone.utc).isoformat(
                           timespec='seconds')},
    }


# ===========================================================================
# IN KẾT QUẢ
# ===========================================================================
def print_report(rep: dict, big=0.25) -> None:
    for run in rep['runs']:
        tag = '  [lịch tải đổi -> giả định nhu cầu đứng yên bị phá]' if run['demand_changes'] else ''
        print('\n== %s%s' % (run['run_id'], tag))
        shown = [r for r in run['rates'] if abs(r['err']) >= big]
        print('   %d chiều link được chấm; %d chiều sai >= %.2f Mbps' % (
            len(run['rates']), len(shown), big))
        for r in sorted(shown, key=lambda r: -abs(r['err'])):
            print('   %-10s dự đoán %6.2f  đo %6.2f  sai %+6.2f  [%s]' % (
                r['dlink'], r['pred'], r['meas'], r['err'], r['zone']))
        for r in run['losses']:
            print('   mất %-8s dự đoán %5.1f%%  đo %5.1f%%  sai %+5.1f điểm  [%s]' % (
                r['link'], r['pred_pct'], r['meas_pct'], r['err_pp'], r['zone']))
        for d in run['post_hoc_diagnostics']:
            print('   [hậu nghiệm] %s: hàng đợi đầy sau ~%.1f s -> mất gói từ tick ~%.1f; '
                  'đo: từ tick %s, sau đó mất trung bình %.1f%% (dự đoán %.1f%%)' % (
                      d['link'], d['fill_time_s_pred'], d['first_loss_tick_pred'],
                      d['first_loss_tick_meas'], d['loss_after_fill_meas_pct'],
                      d['loss_pred_pct']))
    print('\n=== TỔNG KẾT tải từng chiều (Mbps)')
    for zone, s in rep['summary_rates_mbps'].items():
        print('   %-13s n=%-3d trung vị |sai| %.3f  lớn nhất %.2f  trung vị sai tương đối %.1f%%'
              '  tỉ lệ sai <= 10%%: %.0f%%' % (zone, s['n'], s['median_abs'], s['max_abs'],
                                                100 * s['median_rel'],
                                                100 * s['share_rel_le_10pct']))
    print('=== TỔNG KẾT mất gói (điểm phần trăm)')
    for zone, s in rep['summary_loss_pp'].items():
        print('   %-13s n=%-3d trung vị |sai| %.1f  lớn nhất %.1f' % (
            zone, s['n'], s['median_abs'], s['max_abs']))


def main(argv=None):
    rep = validate()
    C.atomic_json(C.ROOT / OUT, rep)
    print_report(rep)
    print('\nreceipt: %s' % OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
