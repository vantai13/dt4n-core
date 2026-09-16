#!/usr/bin/env python3
"""Lesson 5.5 — Chồng feature chứng nhân lên vùng nhãn. Kiểm tra BẰNG MẮT.

Usage: python -m scripts.plot_labels [--root .]

VI SAO CAN, KHI DA CO GATE TU DONG:
    Gate tra loi "co tin hieu trong cua so nhan khong" (co/khong). Mat tra
    loi "tin hieu BAT DAU dung cho khong" — va do la cau hoi khac. Nhan lech
    MOT tick thi gate van xanh (tin hieu van nam trong cua so), nhung mat
    thay ngay duong cong nhay sau vach do.

    Doc du lieu tu ground_truth.json (verify_labels.py da sinh), khong doc lai
    raw: mot nguon so lieu, hai cach trinh bay. Neu doc lai raw, hai file co
    the tinh khac nhau ma khong ai biet.
"""
import argparse
import json
from pathlib import Path

from ml import campaign as C
from ml import labels as L


def plot(root: Path):
    data = json.loads((root / 'results/report/ground_truth.json').read_text())
    timing = data['receipt']['signal_timing']
    tables = {t['run_id']: t for t in data['tables']}
    fault_ids = sorted(timing)
    if not fault_ids:
        raise ValueError('khong co run fault nao trong ground_truth.json')

    import matplotlib
    matplotlib.use('Agg')          # backend không cần màn hình (chạy qua SSH)
    import matplotlib.pyplot as plt

    ncol = 2
    nrow = (len(fault_ids) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(7 * ncol, 2.8 * nrow),
                             squeeze=False)
    for ax, rid in zip(axes.ravel(), fault_ids):
        info, tb = timing[rid], tables[rid]
        ticks = tb['ticks']
        values = info['witness_values']
        inject, revert = info['inject_tick'], info['revert_tick']

        # 1. Vùng NHÃN y=1: tick inject+1 .. revert
        ax.axvspan(inject + 0.5, revert + 0.5, color='#d5773f', alpha=0.18,
                   label='y = 1 (fault)')
        # 2. Dải chuyển tiếp: nhãn không đổi, chỉ bị loại khỏi chỉ số PHỤ
        ax.axvspan(inject + 0.5, inject + 0.5 + tb['grace_onset_ticks'],
                   color='#888888', alpha=0.28, hatch='//',
                   label='dai chuyen tiep (chi so phu loai)')
        ax.axvspan(revert + 0.5, revert + 0.5 + tb['grace_recovery_ticks'],
                   color='#888888', alpha=0.28, hatch='//')
        # 3. Warmup: loại ở MỌI chỉ số
        ax.axvspan(-0.5, tb['warmup_ticks'] - 0.5, color='#aaaaaa', alpha=0.45,
                   label='warmup (loai o moi chi so)')
        # 4. Feature chứng nhân. Khoảng trắng = không đo được, KHÔNG phải 0.
        ax.plot(ticks, values, lw=1.4, color='#1f4e79', marker='.', ms=3)
        # 5. Thời điểm tín hiệu ĐO ĐƯỢC xuất hiện
        onset = info['onset_delay_ticks']
        if onset is not None:
            ax.axvline(inject + 1 + onset, color='#c81e1e', ls='--', lw=1.2,
                       label='tin hieu do duoc (onset=+%d tick)' % onset)
        recovery = info['recovery_delay_ticks']
        if recovery is not None:
            ax.axvline(revert + 1 + recovery, color='#20804a', ls=':', lw=1.2, label='phuc hoi do duoc')
        ax.set_title('%s | %s | onset=%s recovery=%s'
                     % (rid, info['witness'], onset,
                        info['recovery_delay_ticks']), fontsize=8)
        ax.set_xlabel('tick', fontsize=7)
        ax.tick_params(labelsize=7)

    for ax in axes.ravel()[len(fault_ids):]:
        ax.axis('off')
    handles, labs = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labs, loc='lower center', ncol=4, fontsize=8)
    fig.suptitle('Lesson 5.5 — nhan vs tin hieu do duoc | quy uoc %s'
                 % L.LABEL_CONVENTION_ID, fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(root / 'results/report/label_overlay.png', dpi=140)
    plt.close(fig)
    print('-> results/report/label_overlay.png (%d run fault)' % len(fault_ids))
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=C.ROOT)
    return plot(p.parse_args().root.resolve())


if __name__ == '__main__':
    raise SystemExit(main())
