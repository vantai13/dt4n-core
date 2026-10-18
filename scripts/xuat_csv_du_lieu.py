#!/usr/bin/env python3
"""
xuat_csv_du_lieu.py — Xuất dữ liệu của detector thành bảng CSV, mỗi dòng là một giây.

Dữ liệu thô (.jsonl) lồng nhiều tầng nên khó mở bằng Excel. Script này làm phẳng mỗi giây thành
một dòng, với ĐÚNG 71 chỉ số mà detector 2.1 dùng, tính bằng chính code của detector
(ml/serve_fast.py: FastOnlineScorer._values), cộng residual lớn nhất của kênh bảo toàn lưu lượng.
Không tự viết lại cách tính, nên số trong CSV trùng với số detector đã thấy.

Ba tệp, ghi vào ket-qua-bao-cao/5.3-phat-hien-bat-thuong/du-lieu/csv/:
    huan-luyen.csv              8 run học detector 2.1
    tap-phat-trien.csv          10 run kiểm tra của tập phát triển (2 bình thường, 8 có sự cố)
    tap-kiem-tra-doc-lap.csv    24 run của tập kiểm tra độc lập
cùng mo-ta-cot.md mô tả từng cột.

Quy ước: ô không đo được để TRỐNG (không điền 0). Nhãn theo quy ước của dữ liệu:
nhan = 1 khi tick tạo sự cố < tick <= tick gỡ sự cố.

    .venv/bin/python scripts/xuat_csv_du_lieu.py           # ghi lại ba tệp
    .venv/bin/python scripts/xuat_csv_du_lieu.py --check   # tính lại trong bộ nhớ, so với tệp đã lưu

--check còn kiểm min, max của từng cột trên dữ liệu huấn luyện (bỏ giây khởi động) bằng đúng
biên trong models/envelope-2.1.0.json. Mã thoát 1 nếu có gì lệch.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.release import DetectorRelease  # noqa: E402
from ml.serve_fast import FastOnlineScorer  # noqa: E402

RELEASE = ROOT / 'models/detector-release-2.1.0.json'
OUT = ROOT / 'ket-qua-bao-cao/5.3-phat-hien-bat-thuong/du-lieu/csv'
SETS = {
    'huan-luyen': '5.3-phat-hien-bat-thuong/du-lieu/huan-luyen',
    'tap-phat-trien': '5.3-phat-hien-bat-thuong/du-lieu/tap-phat-trien',
    'tap-kiem-tra-doc-lap': '5.3-phat-hien-bat-thuong/du-lieu/tap-kiem-tra-doc-lap',
}
INFO = ['run_id', 'nhom', 'loai_su_co', 'vi_tri_su_co', 'tai_mbps', 'tick', 'nhan', 'khoi_dong']


def run_sources(folder: str) -> list[tuple[str, Path]]:
    """(run_id, đường dẫn .jsonl GỐC) theo danh sách trong dong_bo_ket_qua_bao_cao.py."""
    spec = importlib.util.spec_from_file_location('dong_bo', ROOT / 'scripts/dong_bo_ket_qua_bao_cao.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = []
    for src, name in mod.MAP[folder]:
        if name.endswith('.jsonl'):
            out.append((name[:-len('.jsonl')], ROOT / src))
    return sorted(out)


def build(set_name: str, scorer: FastOnlineScorer) -> pd.DataFrame:
    columns = list(scorer.model.columns)
    rows = []
    for run_id, path in run_sources(SETS[set_name]):
        meta = json.loads(path.with_name(run_id + '.meta.json').read_text(encoding='utf-8'))
        record = meta['record']
        ticks = {e['kind']: e['tick'] for e in meta.get('events', [])}
        inject, revert = ticks.get('inject'), ticks.get('revert')
        warmup = int(meta['constants']['warmup_ticks'])
        load = record.get('load_mbps_per_client')
        info = {
            'run_id': run_id,
            'nhom': record['group'],
            'loai_su_co': record.get('fault') or '',
            'vi_tri_su_co': record.get('fault_target') or '',
            'tai_mbps': 'thay đổi' if record.get('load_schedule') else load,
        }
        for line in path.read_text(encoding='utf-8').splitlines():
            snap = json.loads(line)
            tick = int(snap['tick'])
            row, values, _missing = scorer._values(snap)
            _judgeable, r_max, _switch, _alarm = scorer._conservation(row)
            out = dict(info)
            out['tick'] = tick
            out['nhan'] = int(inject is not None and inject < tick <= revert)
            out['khoi_dong'] = int(tick < warmup)
            out.update(zip(columns, values.tolist()))
            out['residual.r_max'] = r_max
            rows.append(out)
    df = pd.DataFrame(rows, columns=INFO + columns + ['residual.r_max'])
    return df.replace([np.inf, -np.inf], np.nan)


def to_csv_text(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False, lineterminator='\n', na_rep='')
    return buf.getvalue()


def check_bounds(train: pd.DataFrame, model) -> list[str]:
    problems = []
    rows = train[train['khoi_dong'] == 0]
    for column, b in model.bounds.items() if hasattr(model, 'bounds') else model._c['bounds'].items():
        s = pd.to_numeric(rows[column], errors='coerce')
        if not (math.isclose(float(s.min()), b['min'], rel_tol=0, abs_tol=1e-9)
                and math.isclose(float(s.max()), b['max'], rel_tol=0, abs_tol=1e-9)):
            problems.append('%s: CSV [%r, %r] != mô hình [%r, %r]' % (
                column, float(s.min()), float(s.max()), b['min'], b['max']))
    return problems


def describe(columns: list[str], families: dict) -> str:
    rate, indicator = set(families['rate_shared']), set(families['indicator'])
    unit = {'rxRate': 'byte/s', 'txRate': 'byte/s', 'lossPct': '%', 'qdiscDropDelta': 'gói/giây',
            'qdiscSentDelta': 'gói/giây', 'state_up': '1 = up, 0 = down'}
    meaning = {
        'rxRate': 'tốc độ nhận', 'txRate': 'tốc độ gửi', 'lossPct': 'tỉ lệ gói bị bỏ ở hàng đợi, cả hai chiều link',
        'qdiscDropDelta': 'số gói bị bỏ ở hàng đợi trong giây đó, cả hai chiều link',
        'qdiscSentDelta': 'số gói đã gửi qua hàng đợi trong giây đó, cả hai chiều link',
        'state_up': 'trạng thái bật, tắt',
    }
    agg = {
        'agg.rate_absz_max': ('độ lệch lớn nhất của các cột tốc độ link so với trung bình huấn luyện, tính theo số lần độ lệch chuẩn', ''),
        'agg.rate_absz_n_above_3': ('số cột tốc độ link lệch quá 3 lần độ lệch chuẩn', 'cột'),
        'agg.loss_max': ('tỉ lệ mất gói lớn nhất trong 8 link', '%'),
        'agg.loss_n_above_alert': ('số link có tỉ lệ mất gói trên 1%', 'link'),
        'agg.links_down': ('số link đang tắt', 'link'),
    }
    lines = [
        '# Mô tả cột của các tệp CSV',
        '',
        'Sinh tự động bởi `scripts/xuat_csv_du_lieu.py`. Mỗi dòng là một giây của một run. Ô trống là',
        'không đo được (ví dụ giây khởi động, hoặc bộ đếm vừa bị đặt lại), không phải 0.',
        '',
        '## Cột thông tin',
        '',
        '| Cột | Ý nghĩa |',
        '|---|---|',
        '| `run_id` | tên run, trùng tên tệp `.jsonl` trong `../huan-luyen/`, `../tap-phat-trien/`, `../tap-kiem-tra-doc-lap/` |',
        '| `nhom` | N, C: bình thường. F: có sự cố (tập phát triển). RD giảm băng thông, RC flood và dịch nút cổ chai, RN tải cao, RS chạy nền 60 phút, RO tắt link bằng controller (không dùng trong báo cáo) |',
        '| `loai_su_co`, `vi_tri_su_co` | loại và vị trí sự cố, trống nếu run không có sự cố |',
        '| `tai_mbps` | tải mỗi máy khách, Mbps, hoặc "thay đổi" nếu tải đổi theo lịch |',
        '| `tick` | giây thứ mấy trong run, bắt đầu từ 0 |',
        '| `nhan` | 1 nếu giây đó nằm trong khoảng có sự cố (sau giây tạo, tới hết giây gỡ), 0 nếu không |',
        '| `khoi_dong` | 1 ở giây đầu, khi chưa tính được tốc độ. Mô hình bỏ các giây này khi học |',
        '',
        '## 71 cột detector dùng',
        '',
        'Đơn vị: tốc độ tính bằng byte/s, đổi sang Mbps thì nhân 8 rồi chia 10^6.',
        '',
        '| Cột | Nhóm | Ý nghĩa | Đơn vị |',
        '|---|---|---|---|',
    ]
    for column in columns:
        group = 'tốc độ' if column in rate else ('chỉ báo' if column in indicator else '')
        if column in agg:
            text, u = agg[column]
        else:
            thing, _feature, prop = column.split('.', 2)
            text = '%s của %s' % (meaning.get(prop, prop), thing)
            u = unit.get(prop, '')
        lines.append('| `%s` | %s | %s | %s |' % (column, group, text, u))
    lines += [
        '',
        '## Cột thêm',
        '',
        '| Cột | Ý nghĩa |',
        '|---|---|',
        '| `residual.r_max` | residual lớn nhất trên ba switch của kênh bảo toàn lưu lượng (Mục 3.4.3), (vào - ra) / max(vào, 10^4 byte/s) |',
        '',
    ]
    return '\n'.join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    release = DetectorRelease.load(RELEASE)
    scorer = FastOnlineScorer(release.model,
                              expected_collector_version=release.content['collector_version'],
                              conservation=release.conservation, conservation_mode='active')
    bad = 0
    frames = {}
    for name in SETS:
        df = build(name, scorer)
        frames[name] = df
        text = to_csv_text(df)
        target = OUT / (name + '.csv')
        if args.check:
            same = target.exists() and target.read_text(encoding='utf-8') == text
            bad += not same
            print('%-22s %6d dòng  %s' % (name, len(df), 'KHỚP' if same else 'LỆCH hoặc thiếu'))
        else:
            OUT.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')
            print('%-22s %6d dòng  %d run  -> %s' % (name, len(df), df['run_id'].nunique(),
                                                    target.relative_to(ROOT)))
    desc = describe(list(release.model.columns), release.model.families)
    if args.check:
        same = (OUT / 'mo-ta-cot.md').exists() and (OUT / 'mo-ta-cot.md').read_text(encoding='utf-8') == desc
        bad += not same
        print('%-22s         %s' % ('mo-ta-cot.md', 'KHỚP' if same else 'LỆCH hoặc thiếu'))
    else:
        (OUT / 'mo-ta-cot.md').write_text(desc, encoding='utf-8')
    problems = check_bounds(frames['huan-luyen'], release.model)
    print('Biên trên dữ liệu huấn luyện so với mô hình: %s' % (
        'KHỚP 71/71 cột' if not problems else 'LỆCH %d cột' % len(problems)))
    for p in problems[:10]:
        print('  - ' + p)
    bad += bool(problems)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
