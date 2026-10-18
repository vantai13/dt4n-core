#!/usr/bin/env python3
"""Hình 5.1 của báo cáo: độ trễ đồng bộ lên và độ trễ lệnh, xếp từ nhỏ tới lớn.

Đọc:  5.1-phan-chieu-trang-thai/do-tre-dong-bo-len.json   (30 lần đo độ trễ đồng bộ lên)
      5.2-dieu-khien-tu-xa/do-tre-lenh.json               (30 lần đo độ trễ lệnh)
Ghi:  5.1-phan-chieu-trang-thai/hinh/do-tre-xep-hang.pdf và .png

Mỗi chấm là một lần đo. Trục ngang là thứ hạng của lần đo sau khi xếp từ nhỏ tới lớn, nên
nếu các chấm nằm gần một đường thẳng thì độ trễ rải đều trong khoảng đo được.
Chạy bằng ../ve_hinh.sh.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hinh-va-bang'))
import kieu_hinh as K  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

RA = Path(__file__).resolve().parent


def main():
    chuoi = [('Đồng bộ lên', K.KET_QUA / '5.1-phan-chieu-trang-thai/do-tre-dong-bo-len.json', K.XANH, 4),
             ('Lệnh xuống', K.KET_QUA / '5.2-dieu-khien-tu-xa/do-tre-lenh.json', K.CAM, -11)]
    fig, ax = plt.subplots(figsize=(4.6, 2.8))
    for nhan, tep, mau, lech in chuoi:
        ms = sorted(v * 1000 for v in K.doc_json(tep)['result']['latencies_sec'])
        ax.plot(range(1, len(ms) + 1), ms, color=mau, lw=1.5, marker='o', ms=3.2,
                markeredgecolor='white', markeredgewidth=0.6, label=f'{nhan} (n = {len(ms)})')
        ax.annotate(nhan, (len(ms), ms[-1]), xytext=(4, lech), textcoords='offset points',
                    fontsize=8, color=K.XAM_DAM)
    ax.set_xlim(0, 37)
    ax.set_ylim(0, 1100)
    ax.set_xlabel('Thứ hạng của mẫu (từ nhỏ tới lớn)')
    ax.set_ylabel('Độ trễ (ms)')
    ax.yaxis.set_major_formatter(K.PHAY)
    ax.legend(frameon=False, fontsize=8, loc='upper left')
    K.truc(ax)
    fig.tight_layout()
    K.luu(fig, RA, 'do-tre-xep-hang')


if __name__ == '__main__':
    main()
