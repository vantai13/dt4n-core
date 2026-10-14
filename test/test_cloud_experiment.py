"""Test GĐ1.5 — script thí nghiệm, chạy trong một THẾ GIỚI GIẢ có đồng hồ mô phỏng.

Một lượt thật mất vài phút; ở đây đồng hồ được "tua", nên cả lượt chạy trong tích tắc.
Kiểm: số đo từng chặng, PASS/FAIL/INVALID, đối chứng âm, cân bằng tải, cách đếm lượt.
Chạy:
    python3 -m pytest -q test/test_cloud_experiment.py
"""
import random

import pytest

from cloud import experiment as E


class World:
    """Thế giới giả theo kịch bản thời gian (giây, tính từ lúc tiêm sự cố)."""

    def __init__(self, scenario, double_apply=False, never_clean=False,
                 replace_changes_desired=False):
        self.t = 1000.0
        self.scenario = scenario
        self.t_inj = None
        self.act_rows = []
        self.double_apply = double_apply
        self.never_clean = never_clean
        self.replace_changes_desired = replace_changes_desired
        self.base_desired = 1 if scenario in ('replace', 'lb') else 0

    # --- đồng hồ ---
    def clock(self):
        return self.t

    def sleep(self, dt):
        self.t += dt
        self._emit_actions()

    def rel(self):
        return None if self.t_inj is None else self.t - self.t_inj

    def _emit_actions(self):
        """Bộ điều khiển giả: ghi audit 'applied' lúc +8 s (và +9 s nếu double_apply)."""
        r = self.rel()
        if self.scenario not in ('flood', 'linkdown') or r is None:
            return
        marks = [8.0] + ([9.0] if self.double_apply else [])
        for i, m in enumerate(marks):
            cid = 'c%d' % i
            if r >= m and not any(x['cid'] == cid for x in self.act_rows):
                t = self.t_inj + m
                self.act_rows += [
                    {'kind': 'intent', 'cid': cid, 'action': 'set_capacity',
                     'dry_run': False, 't_wall': t},
                    {'kind': 'result', 'cid': cid, 'outcome': 'applied', 't_wall': t + 0.2}]

    # --- twin giả ---
    def sample(self):
        r = self.rel()
        s = {'t': self.t, 'srv1': 'up', 'rho': 0.1, 'pollOk': True, 'cloudAge': 2.0,
             'ctlMode': 'ACTIVE', 'ctlDry': False, 'ctlAge': 1.0,
             'desired': self.base_desired, 'total': self.base_desired,
             'inService': self.base_desired, 'healthy': self.base_desired,
             'ids': ['i-a'] if self.base_desired else []}
        if self.never_clean:
            s.update(desired=1, total=1)
        if self.scenario in ('replace', 'lb'):
            s.update(ctlAge=999.0)                       # bộ điều khiển đã tắt
        if r is None:
            return s
        if self.scenario in ('flood', 'linkdown'):
            if self.scenario == 'flood' and 2 <= r < 62:
                s['rho'] = 0.95
            if self.scenario == 'linkdown' and r >= 1 and not getattr(self, 'recovered', False):
                s['srv1'], s['rho'] = 'down', 0.0
            if 8 <= r < 200:
                s.update(desired=2 if (self.double_apply and r >= 9) else 1, total=1)
            if 70 <= r < 200:
                s['inService'] = 1
            if 100 <= r < 200:
                s['healthy'] = 1
            if r >= 210:
                s.update(desired=0, total=0, inService=0, healthy=0)
        if self.scenario == 'replace':
            if r >= 10:
                s['healthy'] = 0
            if r >= 20:
                s['ids'] = ['i-a', 'i-b']
            if r >= 40:
                s['ids'] = ['i-b']
            if r >= 120:
                s['healthy'] = 1
            if self.replace_changes_desired and 30 <= r < 60:
                s['desired'] = 2
        return s

    def inject(self, scenario, pre):
        self.t_inj = self.t
        return {'victim': 'i-a'} if scenario == 'replace' else {'command': 'x'}

    def recover(self, scenario, info):
        self.recovered = True


def _run(world, tmp_path, **kw):
    return E.run_trial(world.scenario, 1, world.sample, world.inject, world.recover,
                       lambda: world.act_rows, random.Random(1), clock=world.clock,
                       sleep=world.sleep, trials_path=tmp_path / 't.jsonl',
                       log_dir=tmp_path, **kw)


def test_flood_pass(tmp_path):
    rec = _run(World('flood'), tmp_path)
    assert rec['outcome'] == 'PASS', rec['reason']
    seg = rec['metrics']['seg']
    assert 2.0 <= seg['inject_to_onset_s'] <= 3.0
    assert 5.0 <= seg['onset_to_decision_s'] <= 6.0
    assert seg['decision_to_applied_s'] == 0.2
    assert 61.0 <= seg['applied_to_inservice_s'] <= 63.0
    assert 29.0 <= seg['inservice_to_healthy_s'] <= 31.0
    assert rec['metrics']['recover_to_zero_s'] is not None
    assert (tmp_path / 't.jsonl').exists()


def test_linkdown_pass(tmp_path):
    rec = _run(World('linkdown'), tmp_path)
    assert rec['outcome'] == 'PASS', rec['reason']
    assert 1.0 <= rec['metrics']['seg']['inject_to_onset_s'] <= 2.0


def test_hai_lenh_applied_la_fail(tmp_path):
    rec = _run(World('flood', double_apply=True), tmp_path)
    assert rec['outcome'] == 'FAIL'
    assert '2 lệnh' in rec['reason'] or 'vượt' in rec['reason']


def test_he_khong_sach_la_invalid_va_van_duoc_ghi(tmp_path):
    rec = _run(World('flood', never_clean=True), tmp_path)
    assert rec['outcome'] == 'INVALID' and 'chưa về 0' in rec['reason']
    assert 'INVALID' in (tmp_path / 't.jsonl').read_text()


def test_replace_pass_va_giu_so_luong(tmp_path):
    rec = _run(World('replace'), tmp_path)
    assert rec['outcome'] == 'PASS', rec['reason']
    m = rec['metrics']
    assert m['desired_constant'] is True and m['victim'] == 'i-a'
    assert 119.0 <= m['seg']['inject_to_restored_s'] <= 122.0


def test_replace_doi_desired_la_fail(tmp_path):
    rec = _run(World('replace', replace_changes_desired=True), tmp_path)
    assert rec['outcome'] == 'FAIL' and 'desired' in rec['reason']


@pytest.mark.parametrize('scenario,patch,ok', [
    ('flood', {}, True),
    ('flood', {'ctlDry': True}, False),          # controller đang dry-run -> chưa sẵn sàng
    ('flood', {'rho': 0.6}, False),              # srv1 chưa nhàn
    ('replace', {'ctlAge': 1.0}, False),         # controller còn chạy -> phải tắt
    ('replace', {'ctlAge': 50.0, 'desired': 1, 'healthy': 1, 'total': 1}, True),
    ('lb', {'ctlAge': 50.0, 'desired': 1, 'healthy': 1}, False),   # lb cần >= 2 máy
])
def test_dieu_kien_dau(scenario, patch, ok):
    s = {'t': 0, 'srv1': 'up', 'rho': 0.1, 'pollOk': True, 'cloudAge': 2.0,
         'ctlMode': 'ACTIVE', 'ctlDry': False, 'ctlAge': 1.0,
         'desired': 0, 'total': 0, 'healthy': 0}
    s.update(patch)
    assert E.check_ready(scenario, s)[0] is ok


def test_action_pairs_bo_qua_dry_run():
    rows = [{'kind': 'intent', 'cid': 'a', 'action': 'set_capacity', 'dry_run': True, 't_wall': 5},
            {'kind': 'result', 'cid': 'a', 'outcome': 'dry_run', 't_wall': 5},
            {'kind': 'intent', 'cid': 'b', 'action': 'set_capacity', 'dry_run': False, 't_wall': 6},
            {'kind': 'result', 'cid': 'b', 'outcome': 'applied', 't_wall': 6}]
    assert [i['cid'] for i, _ in E.action_pairs(rows, 0, 10)] == ['b']


def test_quiet_pass_va_fail(tmp_path):
    w = World('quiet')
    rec = E.run_quiet(1, w.sample, lambda: [], clock=w.clock, sleep=w.sleep,
                      trials_path=tmp_path / 'q.jsonl')
    assert rec['outcome'] == 'PASS' and rec['n_samples'] >= 25
    rows = [{'kind': 'intent', 'cid': 'z', 'action': 'set_capacity', 'dry_run': False,
             't_wall': w.t + 10},
            {'kind': 'result', 'cid': 'z', 'outcome': 'applied', 't_wall': w.t + 10}]
    rec2 = E.run_quiet(1, w.sample, lambda: rows, clock=w.clock, sleep=w.sleep,
                       trials_path=tmp_path / 'q.jsonl')
    assert rec2['outcome'] == 'FAIL'


def test_lb(tmp_path):
    w = World('lb')
    w.base_desired = 2
    good = lambda n: ({'i-a': 52, 'i-b': 48}, 0)       # noqa: E731
    bad = lambda n: ({'i-a': 95, 'i-b': 5}, 0)         # noqa: E731
    assert E.run_lb(100, w.sample, good, clock=w.clock, sleep=w.sleep,
                    trials_path=tmp_path / 'l.jsonl')['outcome'] == 'PASS'
    assert E.run_lb(100, w.sample, bad, clock=w.clock, sleep=w.sleep,
                    trials_path=tmp_path / 'l.jsonl')['outcome'] == 'FAIL'


def test_dem_5_luot_khong_invalid_dau_tien_khong_chon_luot_dep():
    recs = ([{'scenario': 'flood', 'outcome': 'INVALID', 'reason': 'x'}]
            + [{'scenario': 'flood', 'outcome': o, 'reason': '' if o == 'PASS' else 'chậm',
                'metrics': {'seg': {'onset_to_healthy_s': 100.0}}}
               for o in ('PASS', 'FAIL', 'PASS', 'PASS', 'PASS', 'PASS', 'PASS')])
    s = E.summarize(recs)['flood']
    assert s['n_counted'] == 5 and s['n_pass'] == 4      # lượt thứ 7 (PASS) KHÔNG được thế chỗ
    assert s['n_invalid_reported'] == 1 and s['fail_reasons'] == ['chậm']
    assert s['segments']['onset_to_healthy_s']['median'] == 100.0
