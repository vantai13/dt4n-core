#!/usr/bin/env python3
"""Hình kiểm mù what-if: tải dự đoán so với tải đo được.

Đọc:  5.4-what-if/kiem-mu-ket-qua.json   (dự đoán ghi trước và số đo của hai tình huống)
Ghi:  5.4-what-if/hinh/whatif-du-doan-vs-do.pdf và .png

Chỉ vẽ các dự đoán tải, đơn vị Mbps. Dự đoán mất gói (%) và thời điểm bắt đầu mất gói (s) khác
đơn vị nên không đặt chung một trục, số liệu của chúng nằm trong bảng kiểm mù.
Điểm nằm trên đường chéo nghĩa là dự đoán đúng bằng số đo. Ô vuông là dự đoán đối chứng,
tức dự đoán cho link không liên quan, nơi mô hình phải đoán là tải không đổi.
Chạy bằng ../ve_hinh.sh.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hinh-va-bang'))
import kieu_hinh as K  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

RA = Path(__file__).resolve().parent


def main():
    ket_qua = K.doc_json(K.KET_QUA / '5.4-what-if/kiem-mu-ket-qua.json')
    muc = [it for case in ket_qua['cases'].values() for it in case['items'] if it['kind'] == 'rate']
    if not muc:
        sys.exit('không có dự đoán tải (rate) nào trong tệp kết quả')
    doi_chung = [it for it in muc if it.get('control')]
    chinh = [it for it in muc if not it.get('control')]

    fig, ax = plt.subplots(figsize=(3.6, 3.4))
    hi = max(max(it['pred'], it['meas']) for it in muc) * 1.1
    ax.plot([0, hi], [0, hi], color=K.XAM, lw=1, ls='--', zorder=1, label='Dự đoán = đo được')
    ax.scatter([it['pred'] for it in chinh], [it['meas'] for it in chinh], s=36, color=K.XANH,
               edgecolor='white', linewidth=1.2, zorder=3, label=f'Dự đoán chính ({len(chinh)})')
    if doi_chung:
        ax.scatter([it['pred'] for it in doi_chung], [it['meas'] for it in doi_chung], s=36,
                   marker='s', color=K.CAM, edgecolor='white', linewidth=1.2, zorder=3,
                   label=f'Đối chứng ({len(doi_chung)})')
    ax.xaxis.set_major_formatter(K.PHAY)
    ax.yaxis.set_major_formatter(K.PHAY)
    ax.set_xlim(0, hi)
    ax.set_ylim(0, hi)
    ax.set_aspect('equal')
    ax.set_xlabel('Tải dự đoán (Mbps)')
    ax.set_ylabel('Tải đo được (Mbps)')
    ax.legend(frameon=False, fontsize=8, loc='upper left')
    K.truc(ax, luoi='both')
    fig.tight_layout()
    K.luu(fig, RA, 'whatif-du-doan-vs-do')


if __name__ == '__main__':
    main()
