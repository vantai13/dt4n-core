#!/usr/bin/env python3
"""
experiment.py — GĐ1.5: chạy thí nghiệm ND4 và đóng gói bằng chứng.

KỊCH BẢN (mỗi kịch bản lặp 5 lượt hợp lệ):
  flood    : bạn bắn UDP h1 -> srv1 ở mininet>; bộ điều khiển phải thêm 1 máy cloud
  linkdown : script gửi disableLink(s2-srv1) qua Ditto; bộ điều khiển phải bù 1 máy
  replace  : script báo 1 máy cloud hỏng; ASG phải thay máy, GIỮ NGUYÊN số lượng
  quiet    : đối chứng âm — tải bình thường N phút; bộ điều khiển KHÔNG được làm gì
  lb       : gửi request qua ALB khi có >= 2 máy; mỗi máy phải nhận một phần

TIÊU CHÍ (khóa TRƯỚC khi chạy — xem CRITERIA bên dưới, được chép vào receipt):
  PASS / FAIL / INVALID. INVALID = điều kiện đầu không đạt (hệ chưa sạch, bộ điều
  khiển sai trạng thái) -> lượt KHÔNG được tính, nhưng VẪN được ghi và báo cáo.
  Bằng chứng = 5 lượt KHÔNG-INVALID ĐẦU TIÊN của mỗi kịch bản, theo thứ tự chạy.
  Không được chọn lượt "đẹp".

CÁCH CHẠY (từ thư mục gốc repo, KHÔNG sudo; Ditto + run_sync + cloud.collector đang chạy):
    python3 -m cloud.experiment trial flood --rep 1        # cần cloud.controller run (thật)
    python3 -m cloud.experiment trial linkdown --rep 1     # cần cloud.controller run (thật)
    python3 -m cloud.experiment trial replace --rep 1 --prep   # TẮT cloud.controller
    python3 -m cloud.experiment quiet --minutes 10         # cần cloud.controller run (thật)
    python3 -m cloud.experiment lb --n 100                 # TẮT controller, có >= 2 máy healthy
    python3 -m cloud.experiment report                     # bảng + receipt
"""

import argparse
import hashlib
import json
import random
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path

from cloud.controller import LINK_ID, POOL_ID, SRV1_ID

RESULTS_DIR = Path('results/cloud')
TRIALS_PATH = RESULTS_DIR / 'gd1_trials.jsonl'
RECEIPT_PATH = RESULTS_DIR / 'gd1_receipt.json'
ACT_AUDIT = Path('logs/cloud_actuator_audit.jsonl')
CTL_AUDIT = Path('logs/cloud_controller_audit.jsonl')
COLLECTOR_LOG = Path('logs/cloud_collector.jsonl')

N_COUNTED = 5
TRIAL_TIMEOUT_S = 600.0       # tiêm sự cố -> phải healthy trong 10 phút
PREP_TIMEOUT_S = 300.0        # chờ hệ sạch tối đa 5 phút, quá -> INVALID
RECOVER_TIMEOUT_S = 420.0     # chờ bớt máy về 0 (cooldown 120 s + nhàn 30 s + AWS)

CRITERIA = {
    'flood': 'PASS nếu trong 600 s kể từ khi twin thấy ρ>0.8: healthy>=1; đúng 1 lệnh '
             'set_capacity applied trong cửa sổ; desired không vượt 1.',
    'linkdown': 'PASS nếu trong 600 s kể từ disableLink: healthy>=1; đúng 1 lệnh '
                'set_capacity applied trong cửa sổ; desired không vượt 1.',
    'replace': 'PASS nếu trong 600 s: máy bị báo hỏng biến mất khỏi nhóm và healthy trở lại '
               'bằng desired ban đầu; desired KHÔNG đổi suốt cửa sổ.',
    'quiet': 'PASS nếu suốt cửa sổ: 0 lệnh applied và desired luôn = 0.',
    'lb': 'PASS nếu 0 lỗi và mỗi máy healthy nhận >= 20% request (khi có 2 máy).',
    'counting': '5 lượt không-INVALID đầu tiên của mỗi kịch bản, theo thứ tự chạy. '
                'INVALID = điều kiện đầu không đạt trong 300 s; được ghi và báo cáo.',
}


# ===========================================================================
# PHẦN 1 — nhìn twin (1 lần / giây trong lúc thí nghiệm)
# ===========================================================================
def _prop(body, feature, key):
    try:
        return body['features'][feature]['properties'][key]
    except (KeyError, TypeError):
        return None


def sample(session):
    """Một ảnh chụp twin cho thí nghiệm: srv1, cloud-pool, và trạng thái bộ điều khiển."""
    from bridge.ditto_reader import extract_t_source, fetch_all_things
    things, meta = fetch_all_things(session, [SRV1_ID, LINK_ID, POOL_ID])
    t = meta['t_read']
    host, link, pool = things.get(SRV1_ID), things.get(LINK_ID), things.get(POOL_ID)
    rx = _prop(host, 'traffic', 'rxRate')
    bw = _prop(link, 'capacity', 'bwMbps') or 20.0
    rho = None if rx is None else (rx * 8.0 / 1e6) / bw
    t_pool = extract_t_source(pool) if pool else None
    t_dec = _prop(pool, 'controller', 'tDecision')
    insts = _prop(pool, 'instances', 'list') or []
    return {
        't': t,
        'srv1': _prop(host, 'status', 'state'),
        'rho': None if rho is None else round(rho, 3),
        'desired': _prop(pool, 'capacity', 'desired'),
        'total': _prop(pool, 'pool', 'total'),
        'inService': _prop(pool, 'pool', 'inService'),
        'healthy': _prop(pool, 'pool', 'healthy'),
        'ids': [i.get('id') for i in insts],
        'pollOk': bool(_prop(pool, 'meta', 'pollOk')),
        'cloudAge': None if not t_pool else round(t - t_pool, 2),
        'ctlMode': _prop(pool, 'controller', 'mode'),
        'ctlDry': _prop(pool, 'controller', 'dryRun'),
        'ctlAge': None if not t_dec else round(t - t_dec, 2),
    }


# ===========================================================================
# PHẦN 2 — HÀM THUẦN: điều kiện đầu, đọc audit, tính số đo, phân loại
# ===========================================================================
def controller_active(s):
    return (s.get('ctlMode') == 'ACTIVE' and s.get('ctlDry') is False
            and s.get('ctlAge') is not None and s['ctlAge'] < 10)


def check_ready(scenario, s):
    """(ok, lý do). Hệ phải 'sạch' trước mỗi lượt — giống require_clean ở Phase 8."""
    if not s.get('pollOk') or s.get('cloudAge') is None or s['cloudAge'] > 20:
        return False, 'cloud collector không tươi'
    if s.get('srv1') != 'up':
        return False, 'srv1 chưa up'
    if scenario in ('flood', 'linkdown', 'quiet'):
        if not controller_active(s):
            return False, 'cloud.controller phải đang chạy THẬT (không dry-run)'
        if s.get('desired') != 0 or s.get('total') != 0:
            return False, 'cloud chưa về 0 máy (desired=%s total=%s)' % (
                s.get('desired'), s.get('total'))
        if s.get('rho') is None or s['rho'] > 0.3:
            return False, 'srv1 chưa nhàn (ρ=%s)' % s.get('rho')
        return True, ''
    if scenario in ('replace', 'lb'):
        if s.get('ctlAge') is not None and s['ctlAge'] < 10 and not s.get('ctlDry'):
            return False, 'TẮT cloud.controller trước (nó sẽ bớt máy giữa chừng)'
        need = 2 if scenario == 'lb' else 1
        d = s.get('desired') or 0
        if d < need or s.get('healthy') != d:
            return False, 'cần desired>=%d và healthy=desired (đang %s/%s)' % (
                need, s.get('desired'), s.get('healthy'))
        return True, ''
    return False, 'kịch bản lạ: %s' % scenario


def read_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def action_pairs(rows, t0, t1, action='set_capacity'):
    """Ghép intent/result theo cid; giữ lệnh THẬT (không dry-run) có intent trong [t0, t1]."""
    results = {r['cid']: r for r in rows if r.get('kind') == 'result'}
    out = []
    for r in rows:
        if (r.get('kind') == 'intent' and r.get('action') == action
                and not r.get('dry_run') and t0 <= r.get('t_wall', -1) <= t1):
            out.append((r, results.get(r['cid'])))
    return out


def first_t(samples, pred, after):
    for s in samples:
        if s['t'] >= after and pred(s):
            return s['t']
    return None


def _d(a, b):
    return None if (a is None or b is None) else round(a - b, 2)


def metrics_scale(scenario, t_inject, samples, act_rows, t_end):
    """flood / linkdown: phát hiện -> lệnh -> máy chạy -> ALB healthy."""
    if scenario == 'flood':
        t_onset = first_t(samples, lambda s: (s.get('rho') or 0) > 0.8, t_inject)
    else:
        t_onset = first_t(samples, lambda s: s.get('srv1') == 'down', t_inject)
    pairs = action_pairs(act_rows, t_inject, t_end)
    applied = [(i, r) for i, r in pairs if r and r.get('outcome') == 'applied']
    t_dec = applied[0][0]['t_wall'] if applied else None
    t_app = applied[0][1]['t_wall'] if applied else None
    t_ins = first_t(samples, lambda s: (s.get('inService') or 0) >= 1, t_app) if t_app else None
    t_hea = first_t(samples, lambda s: (s.get('healthy') or 0) >= 1, t_app) if t_app else None
    win = [s for s in samples if s['t'] >= t_inject and (t_hea is None or s['t'] <= t_hea)]
    max_desired = max([s.get('desired') or 0 for s in win] or [0])
    n_applied = len([1 for i, _ in applied if t_hea is None or i['t_wall'] <= t_hea])

    if t_onset is None:
        outcome, reason = 'FAIL', 'twin không thấy sự cố'
    elif t_hea is None:
        outcome, reason = 'FAIL', 'không đạt healthy>=1 trong thời hạn'
    elif n_applied != 1:
        outcome, reason = 'FAIL', '%d lệnh applied (cần đúng 1)' % n_applied
    elif max_desired > 1:
        outcome, reason = 'FAIL', 'desired vượt 1 (=%d)' % max_desired
    else:
        outcome, reason = 'PASS', ''
    return outcome, reason, {
        't_inject': t_inject, 't_onset': t_onset, 't_decision': t_dec, 't_applied': t_app,
        't_inservice': t_ins, 't_healthy': t_hea,
        'seg': {
            'inject_to_onset_s': _d(t_onset, t_inject),     # twin thấy sự cố
            'onset_to_decision_s': _d(t_dec, t_onset),      # debounce + độ trễ đọc twin
            'decision_to_applied_s': _d(t_app, t_dec),      # lời gọi API AWS
            'applied_to_inservice_s': _d(t_ins, t_app),     # máy ảo khởi động
            'inservice_to_healthy_s': _d(t_hea, t_ins),     # ALB kiểm sức khỏe
            'onset_to_healthy_s': _d(t_hea, t_onset),       # TỔNG từ lúc twin thấy sự cố
        },
        'n_applied': n_applied, 'max_desired': max_desired,
        'cids': [i['cid'] for i, _ in applied],
    }


def metrics_replace(t_inject, samples, victim, d0, pre_ids):
    t_drop = first_t(samples, lambda s: (s.get('healthy') or 0) < d0, t_inject)
    t_new = first_t(samples, lambda s: any(i not in pre_ids for i in s.get('ids') or []),
                    t_inject)
    t_rest = first_t(samples, lambda s: (s.get('healthy') or 0) >= d0
                     and victim not in (s.get('ids') or []), t_inject)
    win = [s for s in samples if s['t'] >= t_inject and (t_rest is None or s['t'] <= t_rest)]
    desired_const = all(s.get('desired') == d0 for s in win)
    if t_rest is None:
        outcome, reason = 'FAIL', 'không phục hồi đủ máy healthy trong thời hạn'
    elif not desired_const:
        outcome, reason = 'FAIL', 'desired bị đổi trong lúc failover'
    else:
        outcome, reason = 'PASS', ''
    return outcome, reason, {
        't_inject': t_inject, 't_drop': t_drop, 't_new_instance': t_new, 't_restored': t_rest,
        'seg': {'inject_to_drop_s': _d(t_drop, t_inject),
                'inject_to_new_instance_s': _d(t_new, t_inject),
                'inject_to_restored_s': _d(t_rest, t_inject),
                'degraded_s': _d(t_rest, t_drop)},
        'victim': victim, 'desired': d0, 'desired_constant': desired_const,
    }


# ===========================================================================
# PHẦN 3 — chạy một lượt (phụ thuộc được truyền vào -> test được bằng thế giới giả)
# ===========================================================================
def append_record(rec, path=TRIALS_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + '\n')


def wait_ready(scenario, sampler, clock, sleep, timeout=PREP_TIMEOUT_S, every=5.0):
    deadline = clock() + timeout
    while True:
        s = sampler()
        ok, why = check_ready(scenario, s)
        if ok:
            return s, ''
        if clock() > deadline:
            return s, why
        print('    … chờ hệ sạch: %s' % why)
        sleep(every)


def run_trial(scenario, rep, sampler, inject, recover, read_act, rng,
              clock=time.time, sleep=time.sleep, timeout=TRIAL_TIMEOUT_S,
              recover_timeout=RECOVER_TIMEOUT_S, trials_path=TRIALS_PATH, log_dir=RESULTS_DIR):
    base = {'scenario': scenario, 'rep': rep, 'trial_id': uuid.uuid4().hex[:8],
            'criteria': CRITERIA[scenario]}
    pre, why = wait_ready(scenario, sampler, clock, sleep)
    if why:
        rec = dict(base, outcome='INVALID', reason=why, t=clock())
        append_record(rec, trials_path)
        return rec

    sleep(rng.uniform(0.0, 5.0))           # ngẫu nhiên pha tiêm so với nhịp hệ (bài P3)
    pre = sampler()
    t_inject = clock()
    info = inject(scenario, pre) or {}
    t_inject = info.get('t_inject', t_inject)   # flood: mốc = lúc bạn bấm Enter
    samples = [pre]

    def done(s):
        if scenario == 'replace':
            return ((s.get('healthy') or 0) >= pre['desired']
                    and info.get('victim') not in (s.get('ids') or []))
        return (s.get('healthy') or 0) >= 1

    while clock() - t_inject < timeout:
        s = sampler()
        samples.append(s)
        if s['t'] > t_inject + 2 and done(s):
            break
        sleep(1.0)
    t_end = clock()

    t_recover = clock()
    recover(scenario, info)
    t_back = None
    if scenario in ('flood', 'linkdown'):          # đo thêm: bao lâu thì bớt máy về 0
        while clock() - t_recover < recover_timeout:
            s = sampler()
            s['phase'] = 'recovery'
            samples.append(s)
            if s.get('desired') == 0 and (s.get('total') or 0) == 0:
                t_back = s['t']
                break
            sleep(2.0)

    if scenario == 'replace':
        outcome, reason, m = metrics_replace(t_inject, samples, info.get('victim'),
                                             pre['desired'], pre['ids'])
    else:
        outcome, reason, m = metrics_scale(scenario, t_inject, samples, read_act(), t_end)
        m['recover_to_zero_s'] = _d(t_back, t_recover)

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    sample_file = Path(log_dir) / ('samples_%s_rep%02d_%s.jsonl' % (scenario, rep, base['trial_id']))
    with open(sample_file, 'w', encoding='utf-8') as f:
        for s in samples:
            f.write(json.dumps(s, sort_keys=True) + '\n')
    rec = dict(base, outcome=outcome, reason=reason, metrics=m, inject_info=info,
               samples_file=str(sample_file), t=clock())
    append_record(rec, trials_path)
    return rec


# ===========================================================================
# PHẦN 4 — tiêm sự cố thật
# ===========================================================================
def send_command(subject, target):
    """Gửi lệnh vào inbox Ditto của controller Thing — đúng đường của dashboard."""
    import requests
    from bridge.ditto_common import DITTO_AUTH, DITTO_BASE_URL, NAMESPACE
    url = '%s/things/%s:controller/inbox/messages/%s?timeout=0' % (
        DITTO_BASE_URL, NAMESPACE, subject)
    requests.post(url, json={'target': target}, auth=DITTO_AUTH, timeout=5,
                  headers={'correlation-id': 'gd15-' + uuid.uuid4().hex[:12]})


def make_real_io(actuator):
    def inject(scenario, pre):
        if scenario == 'linkdown':
            send_command('disableLink', LINK_ID)
            return {'command': 'disableLink', 'target': LINK_ID}
        if scenario == 'flood':
            input('\n👉 Gõ sẵn lệnh dưới ở mininet> (CHƯA Enter). Bấm Enter Ở ĐÂY, rồi\n'
                  '   NGAY LẬP TỨC bấm Enter ở mininet>:\n'
                  '      h1 iperf -c 10.0.0.4 -u -b 30M -t 60 &\n')
            return {'command': 'h1 iperf -c 10.0.0.4 -u -b 30M -t 60 &', 'manual': True,
                    't_inject': time.time()}
        if scenario == 'replace':
            victim = pre['ids'][0]
            r = actuator.replace_instance(victim, reason='gd1.5 replace')
            return {'victim': victim, 'cid': r['cid'], 'outcome': r['outcome']}
        return {}

    def recover(scenario, info):
        if scenario == 'linkdown':
            send_command('enableLink', LINK_ID)
        elif scenario == 'flood':
            print('    (flood tự dừng sau 60 s; đang chờ bộ điều khiển bớt máy về 0)')

    return inject, recover


# ===========================================================================
# PHẦN 5 — đối chứng âm, cân bằng tải, báo cáo
# ===========================================================================
def run_quiet(minutes, sampler, read_act, clock=time.time, sleep=time.sleep,
              trials_path=TRIALS_PATH):
    pre, why = wait_ready('quiet', sampler, clock, sleep)
    if why:
        rec = {'scenario': 'quiet', 'outcome': 'INVALID', 'reason': why, 't': clock()}
        append_record(rec, trials_path)
        return rec
    t0 = clock()
    max_desired, n = 0, 0
    while clock() - t0 < minutes * 60:
        s = sampler()
        max_desired = max(max_desired, s.get('desired') or 0)
        n += 1
        sleep(2.0)
    t1 = clock()
    applied = [p for p in action_pairs(read_act(), t0, t1)
               if p[1] and p[1].get('outcome') == 'applied']
    ok = not applied and max_desired == 0
    rec = {'scenario': 'quiet', 'outcome': 'PASS' if ok else 'FAIL',
           'reason': '' if ok else '%d lệnh applied, max desired=%d' % (len(applied), max_desired),
           'criteria': CRITERIA['quiet'], 'minutes': minutes, 'n_samples': n,
           'n_applied': len(applied), 'max_desired': max_desired, 't0': t0, 't1': t1, 't': t1}
    append_record(rec, trials_path)
    return rec


def run_lb(n, sampler, lbtest, clock=time.time, sleep=time.sleep, trials_path=TRIALS_PATH):
    pre, why = wait_ready('lb', sampler, clock, sleep)
    if why:
        rec = {'scenario': 'lb', 'outcome': 'INVALID', 'reason': why, 't': clock()}
        append_record(rec, trials_path)
        return rec
    counts, errors = lbtest(n)
    shares = {k: v / float(n) for k, v in counts.items()}
    ok = errors == 0 and len(counts) >= 2 and min(shares.values()) >= 0.20
    rec = {'scenario': 'lb', 'outcome': 'PASS' if ok else 'FAIL',
           'reason': '' if ok else 'lỗi=%d, phân bố=%s' % (errors, dict(counts)),
           'criteria': CRITERIA['lb'], 'n': n, 'errors': errors, 'counts': dict(counts),
           'healthy': pre.get('healthy'), 't': clock()}
    append_record(rec, trials_path)
    return rec


def _stats(values):
    v = [x for x in values if x is not None]
    if not v:
        return None
    return {'n': len(v), 'median': round(statistics.median(v), 2),
            'min': round(min(v), 2), 'max': round(max(v), 2)}


def summarize(records):
    """5 lượt không-INVALID ĐẦU TIÊN mỗi kịch bản -> bảng. Không chọn lượt đẹp."""
    out = {}
    for sc in ('flood', 'linkdown', 'replace', 'quiet', 'lb'):
        rows = [r for r in records if r.get('scenario') == sc]
        invalid = [r for r in rows if r.get('outcome') == 'INVALID']
        counted = [r for r in rows if r.get('outcome') != 'INVALID'][:N_COUNTED]
        passed = [r for r in counted if r['outcome'] == 'PASS']
        seg = {}
        for r in passed:
            for k, v in ((r.get('metrics') or {}).get('seg') or {}).items():
                seg.setdefault(k, []).append(v)
            if (r.get('metrics') or {}).get('recover_to_zero_s') is not None:
                seg.setdefault('recover_to_zero_s', []).append(r['metrics']['recover_to_zero_s'])
        out[sc] = {'n_counted': len(counted), 'n_pass': len(passed),
                   'n_invalid_reported': len(invalid),
                   'fail_reasons': [r['reason'] for r in counted if r['outcome'] == 'FAIL'],
                   'segments': {k: _stats(v) for k, v in seg.items()}}
    return out


def _sha(path):
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def _git_head():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                              text=True, timeout=5).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def build_receipt(trials_path=TRIALS_PATH, receipt_path=RECEIPT_PATH):
    records = read_rows(trials_path)
    summary = summarize(records)
    receipt = {
        'what': 'DT4N GĐ1 — bằng chứng ND4 (Auto Scaling, Failover, Load Balancing trên AWS)',
        'criteria': CRITERIA, 'n_counted_per_scenario': N_COUNTED,
        'summary': summary, 'n_records': len(records),
        'provenance': {'git_head': _git_head(), 'generated_at': time.time(),
                       'inputs_sha256': {str(p): _sha(p) for p in (
                           trials_path, ACT_AUDIT, CTL_AUDIT, COLLECTOR_LOG)}},
        'note': 'n=5 chỉ cho thấy cơ chế lặp lại được; không đủ để ước lượng tỉ lệ lỗi thấp '
                '(rule of three: 0/5 lỗi -> cận trên 95% ~ 3/5).',
    }
    Path(receipt_path).parent.mkdir(parents=True, exist_ok=True)
    Path(receipt_path).write_text(json.dumps(receipt, indent=2, ensure_ascii=False),
                                  encoding='utf-8')
    return receipt


SEG_ORDER = ['inject_to_onset_s', 'onset_to_decision_s', 'decision_to_applied_s',
             'applied_to_inservice_s', 'inservice_to_healthy_s', 'onset_to_healthy_s',
             'recover_to_zero_s', 'inject_to_drop_s', 'inject_to_new_instance_s',
             'inject_to_restored_s', 'degraded_s']


def print_report(receipt):
    s = receipt['summary']
    print('\n| Kịch bản | Lượt tính | PASS | INVALID (đã báo) |')
    print('|---|---|---|---|')
    for sc, v in s.items():
        print('| %s | %d | %d | %d |' % (sc, v['n_counted'], v['n_pass'], v['n_invalid_reported']))
    for sc in ('flood', 'linkdown', 'replace'):
        segs = s[sc]['segments']
        if not segs:
            continue
        print('\n%s — các chặng (giây, chỉ lượt PASS): trung vị [min; max]' % sc)
        for k in [x for x in SEG_ORDER if x in segs] + [x for x in segs if x not in SEG_ORDER]:
            v = segs[k]
            if v:
                print('  %-26s %7.1f  [%.1f; %.1f]  n=%d' % (k, v['median'], v['min'],
                                                           v['max'], v['n']))
    for sc in s:
        if s[sc]['fail_reasons']:
            print('\nFAIL %s: %s' % (sc, '; '.join(s[sc]['fail_reasons'])))
    print('\nreceipt: %s' % RECEIPT_PATH)


# ===========================================================================
def main(argv=None):
    p = argparse.ArgumentParser(description='Thí nghiệm GĐ1.5 (ND4)')
    sub = p.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('trial')
    t.add_argument('scenario', choices=['flood', 'linkdown', 'replace'])
    t.add_argument('--rep', type=int, required=True)
    t.add_argument('--seed', type=int, default=20261014)
    t.add_argument('--prep', action='store_true',
                   help='replace: tự đặt 1 máy và chờ healthy trước (controller phải TẮT)')
    q = sub.add_parser('quiet')
    q.add_argument('--minutes', type=float, default=10.0)
    lb = sub.add_parser('lb')
    lb.add_argument('--n', type=int, default=100)
    sub.add_parser('report')
    a = p.parse_args(argv)

    if a.cmd == 'report':
        print_report(build_receipt())
        return

    from bridge.ditto_reader import make_session
    from cloud.actuator import CloudActuator
    session = make_session()
    sampler = lambda: sample(session)          # noqa: E731
    read_act = lambda: read_rows(ACT_AUDIT)    # noqa: E731

    if a.cmd == 'quiet':
        rec = run_quiet(a.minutes, sampler, read_act)
    elif a.cmd == 'lb':
        from cloud.infra import lbtest
        rec = run_lb(a.n, sampler, lbtest)
    else:
        act = CloudActuator()
        if a.scenario == 'replace' and a.prep:
            act.set_capacity(1, reason='gd1.5 prep replace')
            print('    … chờ 1 máy healthy (vài phút)')
        inject, recover = make_real_io(act)
        rng = random.Random(a.seed * 100 + a.rep)
        print('▶ %s lượt %d — %s' % (a.scenario, a.rep, CRITERIA[a.scenario]))
        rec = run_trial(a.scenario, a.rep, sampler, inject, recover, read_act, rng)
    print('\n%s  %s  %s' % ({'PASS': '✅', 'FAIL': '❌', 'INVALID': '⚠️ '}[rec['outcome']],
                            rec['outcome'], rec.get('reason', '')))
    seg = (rec.get('metrics') or {}).get('seg')
    if seg:
        for k, v in seg.items():
            print('   %-26s %s' % (k, '-' if v is None else '%.1f s' % v))


if __name__ == '__main__':
    sys.exit(main())
