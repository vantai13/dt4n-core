#!/usr/bin/env python3
"""Lesson 5.3 — thiết kế ma trận thí nghiệm + provenance.

NGUYÊN TẮC: thiết kế TRƯỚC, chạy SAU. File này là "hợp đồng" của dataset.
Nếu chạy trước rồi mới chọn tập test, bạn đang chọn theo kết quả đẹp — một
dạng leakage không có công cụ nào phát hiện được.

BA LOẠI BIẾN, phải phân biệt (ngôn ngữ thiết kế thí nghiệm):
  - YẾU TỐ ĐIỀU KHIỂN (controlled factor): ta CHỦ ĐỘNG đặt, và phải PHỦ hết
    các mức. Ở đây: mức tải, loại fault, link bị fault.
  - THAM SỐ NHIỄU (nuisance parameter): ta không quan tâm giá trị cụ thể,
    nhưng phải tái lập được. Ở đây: độ sâu degrade, tốc độ flood.
    -> sinh từ seed.
  - NHIỄU GÂY LẪN (confounder): thứ ta KHÔNG đặt mà vẫn trôi theo thời gian
    (máy nóng, bộ nhớ phân mảnh). -> khử bằng NGẪU NHIÊN HÓA THỨ TỰ CHẠY.

VÌ SAO KHÔNG DÙNG `rl.scenarios.make_scenario(seed, spec)` Ở ĐÂY:
    `make_scenario` chọn link bị fault NGẪU NHIÊN từ `toggleable_links`.
    Đúng cho RL (muốn đa dạng), SAI cho một ma trận có chủ đích (muốn PHỦ).
    Với 3 link ứng viên và 8 run, P(bỏ sót một link) ~ 3.9% và phân bố không
    đều. Ở đây link là YẾU TỐ ĐIỀU KHIỂN: đặt tay. Seed chỉ dùng cho THAM SỐ
    NHIỄU.
"""
from __future__ import annotations

import json
import math
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

# --- hằng số thiết kế, chốt một lần ---------------------------------------
DURATION_SEC = 60          # số giây GHI snapshot mỗi run
PRE_ROLL_SEC = 5           # bật traffic rồi CHỜ, trước khi bắt đầu ghi
WARMUP_TICKS = 1           # tick đầu không có mẫu trước -> bỏ (Lesson 5.2)
T_INJECT = 20.0            # giây thứ mấy (kể từ t=0 của dataset) thì inject
T_REVERT = 40.0            # và revert
PERIOD_SEC = 1.0
COLLECTOR_VERSION = 'v3-qdisc-ratevalid'   # đổi vì Lesson 5.2 thêm rateValid
EXEC_ORDER_SEED = 20260915

ALL_LINKS = ('h1-s1', 'h2-s1', 'h3-s1', 's1-s2',
             's1-s3', 's2-s3', 's2-srv1', 's3-srv2')

# Luồng theo bảng định tuyến TĨNH (ditto/routing_table.json).
# Tĩnh = KHÔNG tự reroute: hạ một link thì luồng qua nó KHÔNG chuyển đường,
# nó chỉ chết. Đó là lý do ta dự đoán được chính xác link nào có tín hiệu.
# Các đường dưới đây được đối chiếu với next_hop bởi route_paths().
FLOW_PATHS = {
    ('h1', 'srv1'): ('h1-s1', 's1-s2', 's2-srv1'),
    ('h2', 'srv2'): ('h2-s1', 's1-s3', 's3-srv2'),
    ('h3', 'srv1'): ('h3-s1', 's1-s2', 's2-srv1'),
    ('srv1', 'srv2'): ('s2-srv1', 's2-s3', 's3-srv2'),
}


def flows_through(link: str) -> list[str]:
    """Luồng nào đi qua link này. Dùng để DỰ ĐOÁN link nào sẽ có tín hiệu."""
    return [f'{s}->{d}' for (s, d), path in FLOW_PATHS.items() if link in path]


def expected_affected_links(fault: str, target: str) -> list[str]:
    """Link nào DỰ KIẾN thay đổi khi inject fault này.

    Viết ra TRƯỚC khi chạy. Lesson 5.5 sẽ đối chiếu: nếu thực tế không khớp
    dự đoán, một trong hai chỗ sai (mô hình mạng của ta, hoặc kịch bản) —
    và ta biết ngay chứ không phát hiện ở Phase 6.
    """
    if fault in ('admin_down', 'degrade', 'shift') and target not in ALL_LINKS:
        raise ValueError('unknown link target: '+str(target))
    if fault in ('admin_down', 'degrade'):
        # luồng qua link đó bị chặn/thắt -> mọi link TRÊN CÙNG đường đổi theo
        touched = {target}
        for (s, d), path in FLOW_PATHS.items():
            if target in path:
                touched.update(path)
        return sorted(touched)
    if fault == 'flood':
        src, dst = target.split('->')
        return sorted(FLOW_PATHS[(src, dst)])
    if fault == 'shift':
        touched = set(FLOW_PATHS[('srv1', 'srv2')]) | {target}
        for (s, d), path in FLOW_PATHS.items():
            if target in path:
                touched.update(path)
        return sorted(touched)
    raise ValueError(f'fault không biết: {fault}')


# --- provenance -----------------------------------------------------------
def git_provenance(root: Path | None = None) -> dict:
    """git_hash + git_dirty. `git_dirty=True` cảnh báo commit hash chưa đủ mô tả working tree.

    Vì sao phải ghi `git_dirty`: `git_hash` một mình nói dối. Nếu bạn sửa code
    mà chưa commit, hash vẫn trỏ commit cũ, trong khi dữ liệu sinh ra bởi code
    đã đổi. Ba tuần sau bạn checkout hash đó và KHÔNG tái lập được dataset —
    mà không hiểu vì sao.
    """
    root = Path(root or Path(__file__).resolve().parents[1])

    def git(*args):
        result = subprocess.run(['git', '-C', str(root), *args],
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode:
            raise RuntimeError('Cannot determine Git provenance: '+result.stderr.strip())
        return result.stdout.rstrip('\n')
    status = git('status', '--porcelain')
    return {'git_hash': git('rev-parse', 'HEAD'), 'git_dirty': bool(status),
            'git_dirty_files': [l[3:] for l in status.splitlines()]}


# --- một lần chạy ---------------------------------------------------------
@dataclass(frozen=True)
class RunSpec:
    run_id: str
    group: str                  # 'N' train-normal | 'C' test-control | 'F' test-fault
    split: str                  # 'train' | 'test'
    profile: str                # 'normal' | 'normal_varying'
    load_mbps_per_client: float | None
    load_schedule: tuple | None  # cho profile biến thiên: ((giây, Mbps), ...)
    fault: str | None           # None | 'admin_down' | 'degrade' | 'flood' | 'shift'
    fault_target: str | None
    seed: int
    t_inject: float | None
    t_revert: float | None
    duration_sec: int = DURATION_SEC
    expected_links: tuple = field(default=())

    def expected_anomalous_ticks(self) -> int:
        if self.fault is None:
            return 0
        return sum(self.t_inject <= t * PERIOD_SEC < self.t_revert
                   for t in range(WARMUP_TICKS, int(self.duration_sec / PERIOD_SEC)))


# Lịch tải biến thiên: bậc thang 10 giây. KHÔNG cần mượt — bậc thang đã đủ
# để mô hình học "tải THAY ĐỔI là chuyện bình thường", thứ mà một mức tải
# hằng số không bao giờ dạy được.
SCHEDULE_A = ((0, 1.0), (10, 3.0), (20, 2.0), (30, 5.0), (40, 1.0), (50, 4.0))
SCHEDULE_B = ((0, 4.0), (10, 1.0), (20, 5.0), (30, 2.0), (40, 3.0), (50, 1.0))


def build_matrix() -> list[RunSpec]:
    """Ma trận CORE: 18 run. Tất định — gọi hai lần cho kết quả giống hệt."""
    runs: list[RunSpec] = []

    # --- nhóm N: normal, vào TRAIN. 3 mức cố định x 2 seed + 2 lịch khác nhau = 8 run -----------
    # Nguyên tắc: tải "bình thường" phải ĐA DẠNG. Mô hình chỉ thấy một mức
    # tải sẽ coi MỌI thay đổi tải hợp lệ là bất thường -> FPR cao ngất.
    #
    # Mỗi run một seed DUY NHẤT. Đánh đổi: dùng CÙNG seed cho ba mức tải sẽ
    # là "blocking" (ghép cặp) — giảm phương sai khi SO ba mức với nhau. Nhưng
    # nó phá tính đơn ánh run_id <-> seed, và làm gate `seed_unique` vô nghĩa.
    # Với n = 18 run, lợi ích của blocking nhỏ hơn giá của sự mơ hồ.
    for i, load in enumerate((1.0, 2.0, 4.0)):
        for k in (1, 2):
            seed = 1001 + i * 2 + (k - 1)
            runs.append(RunSpec(
                run_id=f'N-load{load:g}M-s{seed}-r{k}', group='N', split='train',
                profile='normal', load_mbps_per_client=load, load_schedule=None,
                fault=None, fault_target=None, seed=seed,
                t_inject=None, t_revert=None))
    for k, (seed, sched) in enumerate([(1007, SCHEDULE_A), (1008, SCHEDULE_A)], start=1):
        runs.append(RunSpec(
            run_id=f'N-vary-s{seed}-r{k}', group='N', split='train',
            profile='normal_varying', load_mbps_per_client=None,
            load_schedule=sched, fault=None, fault_target=None, seed=seed,
            t_inject=None, t_revert=None))

    # --- nhóm C: normal ĐỐI CHỨNG, vào TEST. 2 run ------------------------
    # BẮT BUỘC. Nếu test chỉ có fault thì KHÔNG đo được false positive rate:
    # không có tick bình thường nào để mô hình báo sai.
    runs.append(RunSpec(
        run_id='C-load2M-s2001-r1', group='C', split='test', profile='normal',
        load_mbps_per_client=2.0, load_schedule=None, fault=None,
        fault_target=None, seed=2001, t_inject=None, t_revert=None))
    runs.append(RunSpec(
        run_id='C-vary-s2002-r1', group='C', split='test',
        profile='normal_varying', load_mbps_per_client=None,
        load_schedule=SCHEDULE_B, fault=None, fault_target=None, seed=2002,
        t_inject=None, t_revert=None))

    # --- nhóm F: fault, vào TEST. 4 loại x 2 mục tiêu = 8 run -------------
    # Nền LUÔN là normal TCP 2 Mbps -> nền tải được giữ như nhóm C; can thiệp là
    # CHÍNH FAULT. Đây là chỗ sửa nhiễu gây lẫn của pilot v2: ở pilot,
    # normal = TCP 2M còn flood = UDP 50M, nên "tải" và "giao thức" lẫn nhau.
    fault_cells = [
        ('admin_down', 's1-s2', 3001), ('admin_down', 's1-s3', 3002),
        ('degrade',    's1-s2', 3003), ('degrade',    's2-s3', 3004),
        ('flood',      'h1->srv1', 3005), ('flood',   'h2->srv2', 3006),
        ('shift',      's1-s2', 3007), ('shift',     's1-s3', 3008),
    ]
    for k, (fault, target, seed) in enumerate(fault_cells, start=1):
        tag = target.replace('->', '_to_')
        runs.append(RunSpec(
            run_id=f'F-{fault}-{tag}-s{seed}-r1', group='F', split='test',
            profile='normal', load_mbps_per_client=2.0, load_schedule=None,
            fault=fault, fault_target=target, seed=seed,
            t_inject=T_INJECT, t_revert=T_REVERT,
            expected_links=tuple(expected_affected_links(fault, target))))
    return runs


def execution_order(runs: list[RunSpec], seed: int = EXEC_ORDER_SEED) -> list[str]:
    """Thứ tự CHẠY ngẫu nhiên hóa, tái lập được bằng seed.

    VÌ SAO BẮT BUỘC: `pilot_diagnostics` của chính bạn đã cảnh báo
    "collection order is confounded". Nếu chạy hết normal rồi mới chạy fault,
    trạng thái máy trôi theo thời gian (nhiệt, cache, phân mảnh bộ nhớ) TRÙNG
    KHỚP với nhãn. Mô hình có thể "phát hiện" bằng cách đọc trạng thái máy.
    Xáo thứ tự làm yếu tố nhiễu đó trở thành nhiễu NGẪU NHIÊN, không còn là
    nhiễu CÓ HỆ THỐNG. Ngẫu nhiên làm kết quả kém chính xác hơn; có hệ thống
    làm kết quả ĐẸP HƠN VÀ SAI.
    """
    from numpy.random import default_rng
    ids = [r.run_id for r in runs]
    rng = default_rng(seed)
    idx = rng.permutation(len(ids))
    return [ids[i] for i in idx]


def snapshot_metadata(run: RunSpec, exec_index: int, prov: dict) -> dict:
    """Khối metadata NHÚNG VÀO MỖI SNAPSHOT.

    `collector_version` là trường quan trọng nhất: `ML_PREFLIGHT.md` cảnh báo
    KHÔNG được trộn lossPct v1 (interface) với v2 (qdisc). Lesson 5.2 thêm
    rateValid -> phải là version THỨ BA. Trường này làm việc trộn nhầm trở
    nên KHÔNG THỂ XẢY RA ÂM THẦM — pipeline sẽ từ chối.
    """
    return {
        'run_id': run.run_id, 'group': run.group, 'split': run.split,
        'profile': run.profile,
        'load_mbps_per_client': run.load_mbps_per_client,
        'load_schedule': list(run.load_schedule) if run.load_schedule else None,
        'fault': run.fault, 'fault_target': run.fault_target,
        't_inject': run.t_inject, 't_revert': run.t_revert,
        'seed': run.seed, 'exec_index': exec_index,
        'period_sec': PERIOD_SEC, 'pre_roll_sec': PRE_ROLL_SEC,
        'warmup_ticks': WARMUP_TICKS, 'duration_sec': run.duration_sec,
        'collector_version': COLLECTOR_VERSION,
        'git_hash': prov['git_hash'], 'git_dirty': prov['git_dirty'],
    }


def route_paths(root: Path | None = None) -> dict:
    """Follow the committed destination-based routing table; reject cycles."""
    root = Path(root or Path(__file__).resolve().parents[1])
    table = json.loads((root / 'ditto/routing_table.json').read_text())
    hosts = {info['name']: (ip, info['attached_to']) for ip, info in table['hosts'].items()}
    result = {}
    for source, dest in FLOW_PATHS:
        ip = hosts[dest][0]
        nodes = [source, hosts[source][1]]
        while nodes[-1] != dest:
            node = table['next_hop'][nodes[-1]][ip]
            if node in nodes:
                raise ValueError('routing cycle')
            nodes.append(node)
        result[(source, dest)] = tuple('-'.join(sorted((a,b))) for a,b in zip(nodes,nodes[1:]))
    return result


def fault_parameters(run: RunSpec) -> dict:
    """Explicit targets; seeded severity chosen to exceed the 2M baseline."""
    from numpy.random import default_rng
    from mininet.topology_meta import baseline_bw, load_spec
    rng = default_rng(run.seed)
    if run.fault is None:
        return {}
    if run.fault == 'admin_down':
        return {'link_key': run.fault_target}
    if run.fault in ('degrade', 'shift'):
        baseline = baseline_bw(load_spec(Path(__file__).resolve().parents[1] / 'ditto/topology_spec.json'))[run.fault_target]
        factor = float(rng.uniform(0.65,0.85) if run.fault_target == 's2-s3' else rng.uniform(0.82,0.94))
        params = {'link_key':run.fault_target, 'factor':factor, 'delay':'2ms', 'baseline':baseline}
        if run.fault == 'shift':
            params.update(flood_src='srv1',flood_dst='srv2',rate_mbps=int(rng.integers(20,41)))
        return params
    if run.fault == 'flood':
        src,dst = run.fault_target.split('->')
        return {'src':src,'dst':dst,'rate_mbps':int(rng.integers(30,61))}
    raise ValueError('unknown fault')


def scenario_for_run(run: RunSpec):
    from rl.scenarios import LinkAdminDown, LinkDegrade, TrafficFlood, CongestionShift
    p = fault_parameters(run)
    if not p:
        return None
    if run.fault == 'admin_down':
        return LinkAdminDown(**p)
    if run.fault == 'degrade':
        return LinkDegrade(**p)
    if run.fault == 'flood':
        return TrafficFlood(**p)
    p['degrade_link'] = p.pop('link_key')
    return CongestionShift(**p)



# --- kiểm tra ma trận TRƯỚC khi chạy -------------------------------------
def expected_base_rate(runs: list[RunSpec]) -> float:
    """Tỉ lệ tick bất thường trong tập TEST, sau khi bỏ warmup.

    Phải tính TRƯỚC khi chạy. Nếu base_rate = 100% (như file injection của
    pilot v2) thì không đo được FPR lẫn detection delay, và ta chỉ biết
    điều đó SAU khi đã tốn 2 ngày chạy.
    """
    test = [r for r in runs if r.split == 'test']
    if not test:
        return 0.0
    usable = sum(max(0, int(r.duration_sec / PERIOD_SEC) - WARMUP_TICKS) for r in test)
    anomalous = sum(r.expected_anomalous_ticks() for r in test)
    return anomalous / usable if usable else 0.0


def validate_matrix(runs: list[RunSpec]) -> dict:
    """Mọi gate của Lesson 5.3, dưới dạng KIỂM TRA CHẠY ĐƯỢC."""
    ids = [r.run_id for r in runs]
    train = {r.run_id for r in runs if r.split == 'train'}
    test = {r.run_id for r in runs if r.split == 'test'}
    loads = {r.load_mbps_per_client for r in runs
             if r.group == 'N' and r.load_mbps_per_client is not None}
    n_vary = sum(1 for r in runs if r.profile == 'normal_varying')
    fault_types = {r.fault for r in runs if r.fault}
    seeds = [r.seed for r in runs]
    base = expected_base_rate(runs)
    fault_in_train = [r.run_id for r in runs if r.split == 'train' and r.fault]
    control_in_test = [r.run_id for r in runs
                       if r.split == 'test' and r.fault is None]
    cfg_seeds: dict = {}
    for r in runs:
        if r.group == 'N':
            cfg_seeds.setdefault((r.profile, r.load_mbps_per_client, r.load_schedule), set()).add(r.seed)
    configs_valid = True
    for r in runs:
        try:
            if r.group not in ('N','C','F') or r.split not in ('train','test') or r.profile not in ('normal','normal_varying'):
                raise ValueError('invalid category')
            if (r.group == 'N') != (r.split == 'train') or (r.group == 'F') != (r.fault is not None):
                raise ValueError('group/split/fault mismatch')
            if r.duration_sec != DURATION_SEC:
                raise ValueError('duration outside locked design')
            if r.profile == 'normal_varying':
                from mininet.traffic import schedule_segments
                schedule_segments(r.load_schedule,r.duration_sec)
                if r.load_mbps_per_client is not None:
                    raise ValueError('conflicting schedule')
            elif r.load_schedule is not None or r.load_mbps_per_client is None or not math.isfinite(r.load_mbps_per_client) or r.load_mbps_per_client <= 0:
                raise ValueError('invalid load')
            if r.fault:
                if not (r.t_inject is not None and r.t_revert is not None and WARMUP_TICKS*PERIOD_SEC <= r.t_inject < r.t_revert < r.duration_sec):
                    raise ValueError('fault window')
                if tuple(expected_affected_links(r.fault,r.fault_target)) != r.expected_links:
                    raise ValueError('incorrect expected links')
            elif any(x is not None for x in (r.fault_target,r.t_inject,r.t_revert)):
                raise ValueError('fault metadata on normal run')
        except (ValueError,KeyError,TypeError):
            configs_valid = False
    touched = {link for r in runs for link in r.expected_links}
    checks = {
        'n_runs': len(runs),
        'run_specs_valid': configs_valid,
        'all_links_covered': set(ALL_LINKS) <= touched,
        'routes_match_committed_table': route_paths() == FLOW_PATHS,
        'n_runs_ge_10': len(runs) >= 10,
        'run_id_unique': len(set(ids)) == len(ids),
        'seed_unique': len(set(seeds)) == len(seeds),
        'no_run_in_both_splits': not (train & test),
        'n_normal_load_levels': len(loads),
        'load_levels_ge_3': len(loads) >= 3,
        'has_varying_load_profile': n_vary >= 1,
        'n_fault_types': len(fault_types),
        'fault_types_ge_3': len(fault_types) >= 3,
        'no_fault_in_train': not fault_in_train,
        'test_has_normal_control': len(control_in_test) >= 2,
        'every_normal_config_has_2_seeds': all(len(s) >= 2 for s in cfg_seeds.values()),
        'expected_base_rate': round(base, 4),
        'base_rate_in_10_40_pct': 0.10 <= base <= 0.40,
        'dumb_always_normal_accuracy': round(1 - base, 4),
        'fault_target_covers_links': sorted(
            {r.fault_target for r in runs if r.fault_target}),
    }
    checks['all_pass'] = all(v for k, v in checks.items() if isinstance(v, bool))
    return checks


def matrix_to_records(runs: list[RunSpec], order: list[str]) -> list[dict]:
    pos = {rid: i for i, rid in enumerate(order)}
    if len(order) != len(runs) or len(set(order)) != len(order) or set(order) != {r.run_id for r in runs}:
        raise ValueError('execution order must contain each run exactly once')
    return [dict(asdict(r), exec_index=pos[r.run_id], fault_parameters=fault_parameters(r)) for r in runs]
