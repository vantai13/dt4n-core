#!/usr/bin/env python3
"""Lesson 5.1 — vẽ phân bố normal vs fault cho feature mạnh nhất và yếu nhất.

VÌ SAO PHẢI VẼ: bảng số chỉ cho `mean` và `std`. Hai phân bố có thể cùng
`mean` mà hình dạng khác hoàn toàn (một cái hai đỉnh, một cái một đỉnh). Mắt
người phát hiện được điều đó trong 2 giây; không có con số nào trong bảng
nói hộ.

CHẠY:   python3 -m scripts.plot_feature_audit
RA:     results/report/feature_audit_dist.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use('Agg')                  # không cần màn hình (chạy trên server)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ml.audit import audit_features
from ml.flatten import load_many
from scripts.audit_features import PILOT

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/report'
N_SHOW = 4


def main() -> int:
    df = load_many({ROOT / p: m for p, m in PILOT.items()})
    audit = audit_features(df, fault_col='is_fault')
    # chỉ xét cột ĐO LƯỜNG (numeric). Bỏ qua cờ `qdiscValid` có câu chuyện
    # riêng — nó thuộc Lesson 5.2, không phải bảng xếp hạng tách biệt.
    usable = audit[(audit.quyet_dinh.isin(['GIU', 'CHAT_VAN'])) &
                   (audit.kind == 'numeric')].dropna(subset=['auc_dist'])
    top = usable.nlargest(N_SHOW, 'auc_dist').feature.tolist()
    bot = usable.nsmallest(N_SHOW, 'auc_dist').feature.tolist()

    fig, axes = plt.subplots(2, N_SHOW, figsize=(4.2 * N_SHOW, 7))
    mask = df['is_fault'].astype(bool)
    for j, (title, cols) in enumerate([('TÁCH BIỆT RÕ', top),
                                       ('TÁCH BIỆT YẾU HƠN', bot)]):
        for i, col in enumerate(cols):
            ax = axes[j][i]
            # bool -> float: matplotlib.hist không nhận dtype bool
            s = pd.to_numeric(df[col], errors='coerce').astype(float)
            # BIN DÙNG CHUNG: nếu để mỗi nhóm tự tính bin, nhóm hằng số (ví dụ
            # lossPct ở normal toàn 0) sẽ rơi vào một bin suy biến và BIẾN MẤT
            # khỏi biểu đồ -> người đọc tưởng "không có dữ liệu normal".
            bins = np.histogram_bin_edges(s.dropna(), bins=20)
            ax.hist(s[~mask].dropna(), bins=bins, alpha=.6, label='normal')
            ax.hist(s[mask].dropna(), bins=bins, alpha=.6, label='fault')
            auc = float(audit.set_index('feature').loc[col, 'auc'])
            ax.set_title(f'{col}\nAUC={auc:.3f}', fontsize=8)
            ax.tick_params(labelsize=7)
            if i == 0:
                ax.set_ylabel(f'{title}\nsố mẫu', fontsize=8)
                ax.legend(fontsize=7)
    fig.suptitle('Lesson 5.1 — phân bố normal vs fault (pilot v2, n=150)', fontsize=11)
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'feature_audit_dist.png'
    fig.savefig(path, dpi=130)
    print(f'-> {path}')
    print('mạnh nhất:', top)
    print('yếu nhất :', bot)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
