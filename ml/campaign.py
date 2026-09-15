#!/usr/bin/env python3
"""Lesson 5.4 — logic THUẦN của chiến dịch thu dữ liệu.

VÌ SAO FILE NÀY TỒN TẠI VÀ VÌ SAO NÓ KHÔNG IMPORT MININET:
    `scripts/generate_ml_dataset.py` phải chạy dưới `sudo /usr/bin/python3`
    (Mininet cần root và module mininet nằm ở Python hệ thống). Ở đó KHÔNG có
    numpy/pandas — chúng nằm trong .venv. Nếu logic kiểm tra sống chung với
    code chạm Mininet, bạn chỉ test được nó khi có Mininet + sudo, tức là gần
    như không bao giờ.

    Tách ra: mọi QUYẾT ĐỊNH và mọi KIỂM TRA ở đây, thuần thư viện chuẩn,
    test được bằng dict giả. Mọi thứ chạm mạng ở scripts/.
    Đây đúng là cách bạn đã tách ml/design.py khỏi scripts/build_matrix.py.

NGUYÊN TẮC TRUNG TÂM — THI HÀNH TỪ HỢP ĐỒNG, KHÔNG TÍNH LẠI:
    experiment_matrix.json đã chứa fault_parameters đã được băm vào
    design_content_sha256. Runner ĐỌC chúng, không gọi lại fault_parameters().
    Mỗi lần tính lại là một cơ hội để cái được chạy khác cái đã ký.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / 'results/report/experiment_matrix.json'
RAW_DIR = ROOT / 'data/phase5/raw'
QUARANTINE_DIR = ROOT / 'data/phase5/quarantine'
MANIFEST_PATH = ROOT / 'results/report/ml_dataset_manifest.json'

# Các khóa ĐƯỢC BĂM vào design_content_sha256. PHẢI khớp scripts/build_matrix.py.
# Nếu bạn đổi tập khóa này mà quên đổi bên kia, integrity check sẽ báo lệch
# ở MỌI lần chạy — ồn ào chứ không im lặng. Đó là hành vi đúng.
CONTRACT_KEYS = ('constants', 'runs', 'execution_order', 'split',
                 'routing_table_sha256', 'topology_spec_sha256')

TICK_TOLERANCE = 2          # chênh lệch số snapshot chấp nhận được
MAX_INVALID_FRACTION = 0.05 # trần tỉ lệ mẫu không đo được, ở CỬA SỔ NỀN
GRACE_TICKS = 2             # độ trễ quan sát vật lý sau khi inject
TRAFFIC_MARGIN_SEC = 10     # iperf chạy dư sau khi ghi xong, tránh tắt sớm
MAX_CONSECUTIVE_FAILURES = 2

def canonical_json(obj) -> str:
    """JSON CHUẨN TẮC: cùng nội dung -> cùng chuỗi byte -> cùng hash.

    `sort_keys=True` vì thứ tự khóa trong dict Python không phải ngữ nghĩa.
    `separators=(',', ':')` bỏ mọi khoảng trắng, nếu không thì `indent=2` và
    `indent=4` cho hai hash khác nhau cho cùng một nội dung.

    Đây là khái niệm CANONICALIZATION. Không có nó thì hash vô nghĩa, vì bạn
    đang băm CÁCH TRÌNH BÀY chứ không phải NỘI DUNG.
    """
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    """Băm theo khối 1 MB. File dataset có thể lớn; đừng nạp hết vào RAM."""
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def contract_subset(doc: dict) -> dict:
    """Phần được băm. Thiếu khóa nào là hợp đồng hỏng, không phải bỏ qua."""
    missing = [k for k in CONTRACT_KEYS if k not in doc]
    if missing:
        raise KeyError('hợp đồng thiếu khóa: %s' % missing)
    return {k: doc[k] for k in CONTRACT_KEYS}


def contract_hash(doc: dict) -> str:
    return sha256_bytes(canonical_json(contract_subset(doc)).encode('utf-8'))


def recompute_contract_hash(root: Path | None = None) -> str:
    """Dựng lại ma trận TỪ ml/design.py HIỆN TẠI rồi băm.

    CẦN numpy -> chỉ launcher (.venv) gọi được, runner (sudo python3) thì không.
    Đó là lý do integrity check nằm ở launcher, TRƯỚC khi khởi động gì.
    """
    from ml import design as D            # import lười: runner không chạm tới

    root = Path(root or ROOT)
    runs = D.build_matrix()
    order = D.execution_order(runs)
    subset = {
        'constants': {
            'duration_sec': D.DURATION_SEC, 'pre_roll_sec': D.PRE_ROLL_SEC,
            'warmup_ticks': D.WARMUP_TICKS, 'period_sec': D.PERIOD_SEC,
            't_inject': D.T_INJECT, 't_revert': D.T_REVERT,
            'collector_version': D.COLLECTOR_VERSION,
            'exec_order_seed': D.EXEC_ORDER_SEED,
        },
        'runs': D.matrix_to_records(runs, order),
        'execution_order': order,
        'split': {
            'train': sorted(r.run_id for r in runs if r.split == 'train'),
            'test': sorted(r.run_id for r in runs if r.split == 'test'),
        },
        'routing_table_sha256': sha256_file(root / 'ditto/routing_table.json'),
        'topology_spec_sha256': sha256_file(root / 'ditto/topology_spec.json'),
    }
    return sha256_bytes(canonical_json(subset).encode('utf-8'))


def load_contract(path=CONTRACT_PATH) -> dict:
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    if not doc.get('design_locked'):
        raise RuntimeError('design_locked=False: ma trận chưa đạt gate 5.3, '
                           'không được thu dữ liệu.')
    if doc.get('status') not in ('planned_not_collected', 'collected'):
        raise RuntimeError('status lạ: %r' % doc.get('status'))
    ids = [r['run_id'] for r in doc['runs']]
    if doc.get('n_runs') != len(ids) or len(set(ids)) != len(ids) or sorted(doc['execution_order']) != sorted(ids):
        raise RuntimeError('contract run count/IDs/order inconsistent')
    if set(doc['split']['train']) & set(doc['split']['test']) or set(doc['split']['train']) | set(doc['split']['test']) != set(ids):
        raise RuntimeError('contract split inconsistent')
    return doc


def check_contract_integrity(contract: dict, root: Path | None = None) -> dict:
    """So hash trong file với hash tính lại từ nguồn. Lệch -> DỪNG.

    Hash trong file chỉ bảo vệ khỏi việc SỬA FILE. Nó KHÔNG bảo vệ khỏi việc
    sửa ml/design.py rồi chạy runner: runner đọc file cũ, chạy đúng file cũ,
    nhưng ba tuần sau `build_matrix` sinh ra ma trận khác và bạn không tái lập
    được dataset của chính mình. Đó là DRIFT, và đây là chỗ chặn nó.
    """
    stored = contract.get('design_content_sha256')
    recomputed = recompute_contract_hash(root)
    content = contract_hash(contract)
    ok = (stored == content == recomputed)
    result = {'stored': stored, 'content': content, 'recomputed': recomputed, 'match': ok}
    if not ok:
        raise RuntimeError(
            'HỢP ĐỒNG ĐÃ TRÔI LỆCH.\n'
            '  trong experiment_matrix.json: %s\n'
            '  nội dung JSON hiện tại     : %s\n'
            '  tính lại từ ml/design.py    : %s\n'
            'JSON hoặc mã thiết kế đã đổi sau khi khóa. Kiểm tra diff trước khi chọn:\n'
            '  (a) git checkout ml/design.py  -> giữ hợp đồng cũ, chạy tiếp\n'
            '  (b) python -m scripts.build_matrix -> khóa CHIẾN DỊCH MỚI,\n'
            '      và coi mọi dữ liệu cũ thuộc chiến dịch khác.\n'
            'KHÔNG được ghi đè âm thầm vào chiến dịch đã khóa.'
            % (stored, content, recomputed))
    return result

def traffic_plan(record: dict, constants: dict) -> dict:
    """Từ một dòng hợp đồng -> mô tả CÁCH bật traffic. Hàm THUẦN, test được.

    ĐÂY LÀ CHỖ VÁ LỖI PRE-ROLL.

    Lỗi: hợp đồng có pre_roll_sec=5 (bật tải, chờ 5 s, RỒI mới ghi). Nếu gọi
    start_varying_load(net, SCHEDULE_A, duration=60) thì 5 s pre-roll ăn vào
    bậc đầu tiên, toàn bộ waveform dịch sớm 5 s, và iperf TẮT ở giây thứ 55
    của quá trình ghi -> 5 tick cuối có tải bằng 0.

    Hậu quả nếu bỏ qua: 3 run varying nằm trong tập TRAIN-normal sẽ dạy mô
    hình rằng "tải tụt về 0 là bình thường". Ở Phase 6 nó sẽ bỏ sót đúng loại
    sự cố nghiêm trọng nhất. Dữ liệu vẫn có, chỉ sai ý nghĩa.

    Cách vá: chèn một bậc pre-roll giữ nguyên mức đầu, dịch cả lịch về sau, và
    kéo dài duration thêm biên. Nhờ vậy tại snapshot đầu tiên (t_rel = 0), lịch
    bắt đầu đúng bậc 0 -> waveform ghi được KHỚP `load_schedule` trong metadata.
    """
    pre_roll = float(constants['pre_roll_sec'])
    duration = float(record['duration_sec'])
    iperf_seconds = int(pre_roll + duration + TRAFFIC_MARGIN_SEC)

    if record['profile'] == 'normal_varying':
        schedule = tuple(tuple(x) for x in record['load_schedule'])
        return {'mode': 'varying',
                'schedule_nominal': schedule,
                'schedule_with_preroll': schedule_with_preroll(schedule, pre_roll),
                'iperf_seconds': iperf_seconds,
                'server_bg_rate': 2.0}

    load = record['load_mbps_per_client']
    if load is None or not math.isfinite(load) or load <= 0:
        raise ValueError('run %s: tải cố định không hợp lệ' % record['run_id'])
    return {'mode': 'fixed',
            'normal_rate': '%gM' % load,     # 2.0 -> '2M', khớp start_background_load
            'iperf_seconds': iperf_seconds,
            'server_bg_rate': 2.0}


def schedule_with_preroll(schedule, pre_roll: float):
    """Chèn một bậc pre-roll, giữ nguyên mức của bậc đầu, dịch cả lịch về sau."""
    # This helper is standard-library only despite living in mininet/traffic.
    from mininet.traffic import schedule_with_preroll as prefix
    return prefix(schedule, pre_roll)

def scenario_from_record(record: dict):
    """Dựng đối tượng Scenario TỪ fault_parameters ĐÃ KÝ trong hợp đồng.

    KHÔNG gọi ml.design.scenario_for_run(): hàm đó tính lại tham số bằng numpy
    từ seed. Hai lý do không dùng:
      1. Runner chạy dưới sudo /usr/bin/python3, không có numpy.
      2. Quan trọng hơn: tính lại có thể TRÔI LỆCH khỏi cái đã băm vào
         design_content_sha256. Đọc thẳng thì severity được chạy CHÍNH LÀ
         severity đã ký. Đó là khác biệt giữa "chắc là giống" và "chắc chắn giống".
    """
    fault = record.get('fault')
    if not fault:
        return None
    from rl.scenarios import (CongestionShift, LinkAdminDown, LinkDegrade,
                              TrafficFlood)
    params = dict(record['fault_parameters'])
    if fault == 'admin_down':
        return LinkAdminDown(**params)
    if fault == 'degrade':
        return LinkDegrade(**params)
    if fault == 'flood':
        return TrafficFlood(**params)
    if fault == 'shift':
        params['degrade_link'] = params.pop('link_key')
        return CongestionShift(**params)
    raise ValueError('fault không biết trong hợp đồng: %r' % fault)

def read_snapshots(path) -> list[dict]:
    """Đọc .jsonl. Dòng hỏng thì BÁO, không bỏ qua."""
    snapshots = []
    with open(path, encoding='utf-8') as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                raise ValueError('blank line %d in %s breaks tick indexing' % (i,path))
            try:
                snapshots.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError('dòng %d của %s hỏng: %s' % (i, path, exc))
    return snapshots


def _link_traffic(snapshot):
    """Sinh (link_id, dict traffic) cho mọi Thing kiểu link trong 1 snapshot."""
    for tid, thing in (snapshot.get('things') or {}).items():
        if tid.startswith('link-'):
            yield tid, (thing.get('features') or {}).get('traffic') or {}


CORE_LINK_IDS = ('link-h1-s1','link-h2-s1','link-h3-s1','link-s1-s2',
                 'link-s1-s3','link-s2-s3','link-s2-srv1','link-s3-srv2')

def _invalid_fraction(snapshots, flag):
    """Tỉ lệ mẫu link có `flag` KHÁC True, trên tập snapshot đưa vào."""
    total = invalid = 0
    for snap in snapshots:
        traffic_by_link = dict(_link_traffic(snap))
        for tid in CORE_LINK_IDS:
            total += 1
            invalid += traffic_by_link.get(tid, {}).get(flag) is not True
    return (invalid / total) if total else None, total, invalid


# Sàn tuyệt đối cho mẫu số của độ tách biệt, theo ĐƠN VỊ của từng loại cột.
# VÌ SAO CẦN: công thức Cohen's d chia cho std của nền. Ở normal ổn định,
# std có thể ~0 (pilot v2: rate_std = 0.0217 Mbps, state_up std = 0). Chia cho
# số gần 0 cho ra vài nghìn, và mọi thứ trông như "tách biệt tuyệt vời" kể cả
# khi khác biệt thật chỉ là nhiễu đo. Sàn ép khác biệt phải vượt CẢ nhiễu tự
# nhiên LẪN một ngưỡng có nghĩa vật lý.
SEPARATION_FLOOR = {
    'rxRate': 1.0e4,        # bytes/s  ~ 0.08 Mbps
    'txRate': 1.0e4,
    'lossPct': 0.1,         # phần trăm
    'state_up': 0.01,       # 0/1
}


def separation(baseline: list[float], during: list[float], floor: float):
    """|Δ trung bình| / max(std nền, sàn). Trả None nếu thiếu mẫu."""
    if not math.isfinite(floor) or floor <= 0:
        raise ValueError('separation floor must be finite and positive')
    baseline = [v for v in baseline if math.isfinite(v)]
    during = [v for v in during if math.isfinite(v)]
    if len(baseline) < 3 or len(during) < 3:
        return None
    mu_b = statistics.fmean(baseline)
    mu_d = statistics.fmean(during)
    sigma = statistics.pstdev(baseline)
    return abs(mu_d - mu_b) / max(sigma, floor)


def _probe_series(snapshots, link_id):
    """4 chuỗi dò tín hiệu cho một link. Bỏ mẫu không hợp lệ, KHÔNG điền 0."""
    out = {'rxRate': [], 'txRate': [], 'lossPct': [], 'state_up': []}
    for snap in snapshots:
        thing = (snap.get('things') or {}).get(link_id)
        if thing is None:
            continue
        features = thing.get('features') or {}
        traffic = features.get('traffic') or {}
        if traffic.get('rateValid') is True:
            for key in ('rxRate', 'txRate'):
                value = traffic.get(key)
                if isinstance(value, (int, float)) and not isinstance(value,bool) and math.isfinite(value):
                    out[key].append(float(value))
        if traffic.get('qdiscValid') is True:
            value = traffic.get('lossPct')
            if isinstance(value, (int, float)) and not isinstance(value,bool) and math.isfinite(value):
                out['lossPct'].append(float(value))
        state = (features.get('status') or {}).get('state')
        if state in ('up', 'down'):
            out['state_up'].append(1.0 if state == 'up' else 0.0)
    return out

def signal_check(record, constants, snapshots, inject_tick, revert_tick):
    """Fault này có ĐỂ LẠI DẤU VẾT ĐO ĐƯỢC trên các link đã dự đoán không?

    VÌ SAO KIỂM TRA Ở 5.4 CHỨ KHÔNG ĐỢI 5.5:
        Nếu 8 run fault không có tín hiệu, bạn muốn biết sau 3 phút hay sau
        khi đã chạy hết 70 phút rồi sang lesson sau mới phát hiện? Đây là
        phép kiểm tra rẻ nhất và bắt được lỗi đắt nhất của cả phase.

    Đối chiếu ĐÚNG tập `expected_links` mà Lesson 5.3 suy ra từ bảng định
    tuyến tĩnh. Nếu thực tế không khớp dự đoán, một trong hai chỗ sai: mô hình
    mạng của bạn, hoặc kịch bản. Cả hai đều phải biết NGAY.

    GRACE_TICKS: inject ở tick 20 thì collector chỉ thấy ở chu kỳ quét sau.
    Đây là ĐỘ TRỄ QUAN SÁT VẬT LÝ, có thật trong mọi hệ giám sát, không phải lỗi.
    """
    warmup = int(constants['warmup_ticks'])
    baseline = snapshots[warmup:inject_tick + 1]
    during = snapshots[inject_tick + 1 + GRACE_TICKS:revert_tick + 1]

    per_link = {}
    best = 0.0
    for link_id in ('link-%s' % x for x in record['expected_links']):
        base = _probe_series(baseline, link_id)
        fault = _probe_series(during, link_id)
        scores = {}
        for key, floor in SEPARATION_FLOOR.items():
            value = separation(base[key], fault[key], floor)
            if value is not None:
                scores[key] = round(value, 3)
                best = max(best, value)
        per_link[link_id] = scores
    return {'per_link': per_link,
            'max_separation': round(best, 3),
            'signal_present': best >= 1.0}

def verify_run(record, constants, snapshots, events) -> dict:
    """Mọi gate cho MỘT run. Trả dict; `passed` quyết định giữ hay cách ly."""
    period = float(constants['period_sec'])
    warmup = int(constants['warmup_ticks'])
    expected_ticks = int(round(record['duration_sec'] / period))
    checks: dict = {'n_snapshots': len(snapshots),
                    'expected_ticks': expected_ticks}

    if not snapshots:
        checks.update(tick_count_ok=False, passed=False,
                      reasons=['file rỗng'])
        return checks

    checks['embedded_ticks_ok'] = [s.get('tick') for s in snapshots] == list(range(len(snapshots)))
    checks['tick_count_ok'] = abs(len(snapshots) - expected_ticks) <= TICK_TOLERANCE

    run_ids = {(s.get('run') or {}).get('run_id') for s in snapshots}
    checks['run_id_uniform'] = run_ids == {record['run_id']}

    versions = {(s.get('run') or {}).get('collector_version') for s in snapshots}
    checks['collector_version'] = sorted(str(v) for v in versions)
    checks['collector_version_uniform'] = versions == {constants['collector_version']}

    monotonic = [s.get('t_rel') for s in snapshots]
    checks['t_rel_monotonic'] = all(isinstance(t,(int,float)) and not isinstance(t,bool) and math.isfinite(t) and t>=0 for t in monotonic) and all(
        isinstance(a, (int, float)) and isinstance(b, (int, float)) and b > a
        for a, b in zip(monotonic, monotonic[1:]))

    # --- cửa sổ NỀN: trước khi inject (hoặc cả run nếu là run normal) ---
    inject_tick = next((e.get('tick') for e in events if e.get('kind') == 'inject'), None)
    revert_tick = next((e.get('tick') for e in events if e.get('kind') == 'revert'), None)
    baseline_end = inject_tick + 1 if isinstance(inject_tick,int) else len(snapshots)
    baseline = snapshots[warmup:baseline_end]
    checks['baseline_link_presence_ok'] = bool(baseline) and all(set(CORE_LINK_IDS) <= set(s.get('things') or {}) for s in baseline)

    for flag, name in (('qdiscValid', 'qdisc'), ('rateValid', 'rate')):
        frac, total, bad = _invalid_fraction(baseline, flag)
        checks['%s_invalid_fraction_baseline' % name] = (
            None if frac is None else round(frac, 4))
        checks['%s_samples_baseline' % name] = total
        checks['%s_invalid_ok' % name] = (frac is not None
                                          and frac < MAX_INVALID_FRACTION)
        if isinstance(inject_tick,int):
            during = snapshots[inject_tick + 1:revert_tick + 1 if isinstance(revert_tick,int) else len(snapshots)]
            frac_f, _, _ = _invalid_fraction(during, flag)
            # KHÔNG phải gate. "Không đo được" TRONG lúc có lỗi có thể chính là
            # hệ quả của lỗi (MNAR — Lesson 5.2). Gate ở đây sẽ ép bạn vứt bỏ
            # đúng những mẫu nhiều thông tin nhất. Ghi lại để 5.6 quyết định.
            checks['%s_invalid_fraction_fault' % name] = (
                None if frac_f is None else round(frac_f, 4))

    # --- gate riêng theo loại run ---
    if record.get('fault'):
        t_inject = float(record['t_inject'])
        t_revert = float(record['t_revert'])
        got = {e['kind']: e for e in events}
        checks['events_complete'] = len(events) == 2 and [e['kind'] for e in events] == ['inject','revert']
        checks['event_ticks_ok'] = isinstance(inject_tick,int) and isinstance(revert_tick,int) and 0 <= inject_tick < revert_tick < len(snapshots)
        checks['inject_t_rel'] = got.get('inject', {}).get('t_rel')
        checks['revert_t_rel'] = got.get('revert', {}).get('t_rel')
        checks['inject_on_time'] = (
            'inject' in got
            and isinstance(got['inject'].get('t_rel'),(int,float))
            and math.isfinite(got['inject']['t_rel'])
            and abs(got['inject']['t_rel'] - t_inject) <= 1.5 * period)
        checks['revert_on_time'] = (
            'revert' in got
            and isinstance(got['revert'].get('t_rel'),(int,float))
            and math.isfinite(got['revert']['t_rel'])
            and abs(got['revert']['t_rel'] - t_revert) <= 1.5 * period)
        if checks['event_ticks_ok']:
            checks.update(signal_check(record, constants, snapshots,
                                       inject_tick, revert_tick))
        else:
            checks.update(signal_present=False, max_separation=0.0, per_link={})
        if record['fault'] == 'admin_down':
            target = 'link-%s' % record['fault_target']
            window = snapshots[inject_tick + 1:revert_tick + 1] if checks['event_ticks_ok'] else []
            states = {((s.get('things') or {}).get(target) or {})
                      .get('features', {}).get('status', {}).get('state')
                      for s in window}
            # LinkAdminDown là kịch bản DUY NHẤT làm status.state đổi thật.
            # Lesson 5.1 đã đo: 16 cột status.state_up có nunique=1 trên cả 150
            # snapshot pilot -> bị LOẠI vì hằng số. Nếu 18 run cũng không có mẫu
            # down thật, chúng chết lần nữa, và Phase 7/8 mất loại sự cố rõ nhất.
            checks['admin_down_observed'] = 'down' in states
    else:
        down = sorted({
            tid for s in snapshots
            for tid, thing in (s.get('things') or {}).items()
            if tid.startswith('link-')
            and (thing.get('features', {}).get('status', {}).get('state') == 'down')})
        checks['links_down_in_normal_run'] = down
        # Một run normal mà có link down nghĩa là trạng thái từ run trước còn sót,
        # hoặc revert của run fault trước đó thất bại. Dataset nhiễm bẩn.
        checks['no_unexpected_down'] = not down
        checks['events_complete'] = not events

    reasons = [k for k, v in checks.items()
               if k.endswith(('_ok', '_uniform', '_complete', '_observed',
                              '_on_time', '_present', '_monotonic'))
               or k == 'no_unexpected_down']
    checks['passed'] = all(checks[k] is True for k in reasons)
    checks['failed_gates'] = [k for k in reasons if checks[k] is not True]
    return checks

def measured_base_rate(contract, outcomes) -> dict:
    """Base rate THỰC của tập test, tính từ sự kiện inject/revert ĐÃ XẢY RA.

    Lesson 5.3 tính nominal 27,12% trên lịch chuẩn và tự ghi chú: "Runtime có
    jitter/missing nên sau 5.4 phải tính lại từ timestamp và sự kiện thực."
    Đây chính là phép tính đó.

    Vì sao bắt buộc phải có: một mô hình ngu "luôn nói bình thường" đạt
    accuracy = 1 - base_rate. Không có con số này thì Phase 6 không diễn giải
    được bất kỳ chỉ số nào.
    """
    warmup = int(contract['constants']['warmup_ticks'])
    test_ids = set(contract['split']['test'])
    usable = anomalous = 0
    for run_id, outcome in outcomes.items():
        if run_id not in test_ids or outcome.get('status') != 'ok' or outcome.get('checks',{}).get('passed') is not True:
            continue
        checks = outcome['checks']
        usable += max(0, checks['n_snapshots'] - warmup)
        events = {e['kind']: e for e in outcome.get('events', [])}
        if 'inject' in events and 'revert' in events:
            lo = max(warmup, events['inject']['tick'] + 1)
            hi = min(checks['n_snapshots'], events['revert']['tick'] + 1)
            anomalous += max(0,hi-lo)
    return {'usable_test_ticks': usable,
            'anomalous_test_ticks': anomalous,
            'base_rate_measured': round(anomalous / usable, 4) if usable else None,
            'dumb_always_normal_accuracy': round(1 - anomalous / usable, 4) if usable else None,
            'base_rate_nominal': contract.get('expected_base_rate_test')}

def build_manifest(contract, outcomes, collection_provenance, integrity,
                   started_utc, finished_utc) -> dict:
    expected_ids = {r['run_id'] for r in contract['runs']}
    if not set(outcomes) <= expected_ids:
        raise ValueError('manifest contains a run outside the contract')
    ok = [r for r, o in outcomes.items() if o.get('status') == 'ok' and o.get('checks',{}).get('passed') is True]
    failed = {r: o for r, o in outcomes.items() if r not in ok}
    return {
        'campaign': 'phase5-core-18run',
        'design_content_sha256': contract['design_content_sha256'],
        'contract_integrity': integrity,
        'collection_provenance': collection_provenance,   # git LÚC THU
        'design_provenance': contract['provenance'],       # git LÚC THIẾT KẾ
        'constants': contract['constants'],
        'started_utc': started_utc, 'finished_utc': finished_utc,
        'n_runs_expected': contract['n_runs'],
        'n_runs_ok': len(ok), 'n_runs_failed': len(failed),
        'runs_not_attempted': sorted(expected_ids-set(outcomes)),
        'complete': set(ok) == expected_ids and integrity.get('match') is True,
        'split': contract['split'],
        'runs': outcomes,
        'base_rate': measured_base_rate(contract, outcomes),
        'missing_data_rule': (
            'Không fillna ở tầng thu. Mẫu qdiscValid/rateValid = false được GHI '
            'nguyên trạng; việc lọc do ml/dataset.py ở Lesson 5.6 quyết định.'),
        'warmup_rule': (
            'Tick warmup được GHI, không bị xóa. Lọc tick < warmup_ticks ở tầng '
            'nạp. Nhờ vậy đổi quy tắc warmup không phải chạy lại chiến dịch.'),
    }

# --- đường dẫn: quy ước một chỗ duy nhất ---------------------------------
def run_paths(run_id: str, root: Path | None = None) -> dict:
    """Mọi đường dẫn của một run. Quy ước nằm MỘT chỗ, không rải trong runner.

    `.partial` là COMMIT POINT: chừng nào file còn đuôi .partial thì run chưa
    hoàn tất. Sự TỒN TẠI của <run_id>.jsonl (không .partial) chính là bằng
    chứng run đã chạy xong VÀ đã qua kiểm tra. Nhờ vậy tiến độ chiến dịch nằm
    trên ĐĨA, không nằm trong RAM — runner chết lúc nào cũng khôi phục được,
    không cần file checkpoint riêng.
    """
    root = Path(root or ROOT)
    import re
    if not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',run_id):
        raise ValueError('run_id không hợp lệ cho tên file: %r' % run_id)
    raw = root / 'data/phase5/raw'
    quar = root / 'data/phase5/quarantine'
    return {
        'partial': raw / ('%s.jsonl.partial' % run_id),
        'final':   raw / ('%s.jsonl' % run_id),
        'meta':    raw / ('%s.meta.json' % run_id),
        'quarantine':      quar / ('%s.jsonl' % run_id),
        'quarantine_meta': quar / ('%s.meta.json' % run_id),
        'log': root / ('logs/ml_gen_%s.log' % run_id),
    }


# --- khối metadata nhúng vào MỖI snapshot --------------------------------
def snapshot_meta(record: dict, constants: dict, provenance: dict,
                  design_sha: str) -> dict:
    """Bản sao của ml.design.snapshot_metadata(), dựng từ DICT hợp đồng.

    Vì sao không gọi thẳng design.snapshot_metadata(): hàm đó nhận RunSpec
    (dataclass), còn runner chỉ có dict đọc từ JSON. Dựng lại RunSpec sẽ kéo
    theo ml.design và rủi ro numpy.

    THÊM `design_content_sha256` so với bản của design.py. Lý do: nếu ai đó
    `cat *.jsonl > all.jsonl`, sidecar mất liên kết nhưng khối nhúng sống sót.
    Dữ liệu phải TỰ KHAI nó thuộc chiến dịch nào, kể cả khi bị tách khỏi ngữ cảnh.
    """
    return {
        'run_id': record['run_id'], 'group': record['group'],
        'split': record['split'], 'profile': record['profile'],
        'load_mbps_per_client': record['load_mbps_per_client'],
        'load_schedule': record['load_schedule'],
        'fault': record['fault'], 'fault_target': record['fault_target'],
        't_inject': record['t_inject'], 't_revert': record['t_revert'],
        'seed': record['seed'], 'exec_index': record['exec_index'],
        'period_sec': constants['period_sec'],
        'pre_roll_sec': constants['pre_roll_sec'],
        'warmup_ticks': constants['warmup_ticks'],
        'duration_sec': record['duration_sec'],
        'collector_version': constants['collector_version'],
        'git_hash': provenance['git_hash'],
        'git_dirty': provenance['git_dirty'],
        'source_dirty': provenance.get('source_dirty', provenance['git_dirty']),
        'design_content_sha256': design_sha,
    }


# --- sidecar --------------------------------------------------------------
def build_sidecar(record, constants, checks, events, provenance, design_sha,
                  sha256, reset_info, plan, started_utc, finished_utc) -> dict:
    """Mọi thứ KHÔNG thể nằm trong file .jsonl.

    SHA-256 của một file không thể nằm trong chính file đó: thêm hash làm đổi
    nội dung, làm đổi hash. Nghịch lý tự quy chiếu. Nên nó phải ở đây.

    `reset_info` là output của EnvRunner.soft_reset(). Nó là bằng chứng ĐỊNH
    LƯỢNG rằng run này bắt đầu từ trạng thái sạch: steady_ok, aoi_norm,
    iperf_leaked, health.throughput_norm. Hội đồng hỏi "làm sao em biết run 12
    không nhiễm bẩn từ run 11" thì đây là câu trả lời có số.
    """
    return {
        'run_id': record['run_id'],
        'sha256': sha256,
        'design_content_sha256': design_sha,
        'collection_provenance': provenance,
        'record': record,
        'constants': constants,
        'traffic_plan': plan,
        'reset_info': reset_info,
        'events': events,
        'checks': checks,
        'label_convention': LABEL_CONVENTION,
        'started_utc': started_utc,
        'finished_utc': finished_utc,
    }


LABEL_CONVENTION = 'point-wise; label[t]=1 iff inject_tick < t <= revert_tick; grace=2 ticks'


def labels_from_events(n_snapshots, events):
    if not isinstance(n_snapshots,int) or n_snapshots < 0:
        raise ValueError('invalid snapshot count')
    labels = [0]*n_snapshots
    if not events:
        return labels
    if len(events) != 2 or [e.get('kind') for e in events] != ['inject','revert']:
        raise ValueError('labels require ordered inject and revert events')
    inject,revert = (e.get('tick') for e in events)
    if not isinstance(inject,int) or not isinstance(revert,int) or not 0 <= inject < revert < n_snapshots:
        raise ValueError('event ticks outside snapshot sequence')
    for tick in range(inject+1,revert+1):
        labels[tick]=1
    return labels


def atomic_json(path, data):
    import os
    import tempfile
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=path.parent,prefix=path.name+'.',suffix='.tmp')
    try:
        with os.fdopen(fd,'w') as out:
            json.dump(data,out,indent=2,ensure_ascii=False);out.write('\n');out.flush();os.fsync(out.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def collection_provenance(root=None):
    from ml.design import git_provenance
    prov = git_provenance(root or ROOT)
    runtime = ('logs/', 'data/phase5/', 'results/report/', 'report.html')
    prov['source_dirty_files'] = [p for p in prov['git_dirty_files'] if not p.startswith(runtime)]
    prov['source_dirty'] = bool(prov['source_dirty_files'])
    return prov
