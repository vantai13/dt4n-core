#!/usr/bin/env python3
"""Snapshot JSON lồng nhau -> một bảng phẳng (DataFrame).

QUY ƯỚC CỘT:  <thing_id>.<ditto_feature>.<property>
    ví dụ 'link-h1-s1.traffic.lossPct', 'host-h1.traffic.rxRate'

BA LUẬT BẮT BUỘC (mỗi luật có một test ghim):
    L1. KHÔNG BAO GIỜ fillna. `null` phải đi đến tận DataFrame dưới dạng NaN.
        Điểm khác nhau giữa "đo được 0" và "không đo được" là tài sản đắt
        nhất của dataset này — không được làm mất ở tầng đọc file.
    L2. KHÔNG GỘP 8 link thành trung bình. Một cột cho MỖI link. Gộp lại thì
        mất khả năng định vị link nào có vấn đề.
    L3. Mọi cột suy diễn (ví dụ state_up) phải TÁCH RIÊNG khỏi cột gốc,
        không ghi đè, để còn đối chiếu được.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

UP_STATES = ('up',)


def flatten_snapshot(snap: dict) -> dict:
    """Một snapshot -> một dòng dict. Không đọc dữ liệu lồng cấp 3 (qdiscCounters)."""
    row: dict = {
        'timestamp': snap.get('timestamp'),
        't_source': snap.get('t_source'),
        'cycle_scan_ms': snap.get('cycle_scan_ms'),
    }
    for key, value in (snap.get('run') or {}).items():
        if not isinstance(value, (dict, list)):
            row[key] = value
    for key in ('tick', 't_rel'):
        if key in snap:
            row[key] = snap[key]
    for thing_id, thing in (snap.get('things') or {}).items():
        if 't_source' in thing:
            row[f'{thing_id}.t_source'] = thing['t_source']
        features = thing.get('features') or {}
        for fname, fval in features.items():
            if not isinstance(fval, dict):
                continue
            # Accept collector snapshots and Ditto's properties wrapper.
            fval = fval.get('properties', fval)
            if not isinstance(fval, dict):
                continue
            for prop, val in fval.items():
                if isinstance(val, (dict, list)):
                    continue                      # qdiscCounters: bỏ qua có Ý
                col = f'{thing_id}.{fname}.{prop}'
                row[col] = val
                if prop == 'state':               # L3: suy diễn, không ghi đè
                    row[col + '_up'] = 1 if val == 'up' else 0 if val == 'down' else None
            if fname == 'traffic' and fval.get('qdiscValid') is False:
                row[f'{thing_id}.traffic.lossPct'] = None
    return row


def load_jsonl(path: str | Path, **meta) -> pd.DataFrame:
    """Đọc một file .jsonl -> DataFrame. `meta` được gắn vào mọi dòng."""
    path = Path(path)
    rows = []
    with path.open(encoding='utf-8') as fh:
        for tick, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            row = flatten_snapshot(json.loads(line))
            if row.get('tick') is not None and row['tick'] != tick:
                raise ValueError(f'{path.name} dòng {tick}: embedded tick {row["tick"]} differs from line index; file reordered/cut/concatenated')
            row['tick'] = tick
            row['source_file'] = path.name
            row.update(meta)
            rows.append(row)
    if not rows:
        raise ValueError(f'file rỗng hoặc không có snapshot hợp lệ: {path}')
    # L1: KHÔNG fillna. pd.DataFrame giữ null -> NaN, đúng như ta muốn.
    return pd.DataFrame(rows)


def load_many(spec: dict[str, dict]) -> pd.DataFrame:
    """spec = {path: {meta...}} -> một DataFrame gộp."""
    frames = [load_jsonl(path, **meta) for path, meta in spec.items()]
    if not frames:
        raise ValueError('không có file snapshot để đọc')
    return pd.concat(frames, ignore_index=True, sort=False)
