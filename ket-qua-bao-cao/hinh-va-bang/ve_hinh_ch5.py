#!/usr/bin/env python3
"""Vẽ hai hình của Chương 5 thẳng từ file kết quả của repo dt4n-core.

  Hình 5.1  do-tre-xep-hang.pdf : 30 mẫu độ trễ đồng bộ lên và 30 mẫu độ trễ
            lệnh, xếp từ nhỏ tới lớn (results/report/latency_*_randomized.json).
  Hình 5.x  ab-tung-luot.pdf    : thí nghiệm A/B, mỗi chấm là một lượt, trục
            dọc là tốc độ gửi trung bình của h3 (results/report/gd4cl_ab.json, lần
            chạy lại với detector 2.1; bản Phase 8 ở phase8_ab_c5.json).
            Panel số giây được tính đã bỏ theo bản rút gọn Chương 5 (16/10/2026).

Không gõ tay số nào. Cách chạy (hoặc `make hinh`):
    ~/dt4n-core/.venv/bin/python -I scripts/ve_hinh_ch5.py ~/dt4n-core figures
"""
import json
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

# Bảng màu: hai ô đầu của bảng tham chiếu, đã qua bộ kiểm bảng màu
# (CVD ΔE 24,7; normal ΔE 33,6). Chữ dùng màu mực, không dùng màu chuỗi.
BLUE, ORANGE = '#2a78d6', '#eb6834'
INK, MUTED, GRID = '#0b0b0b', '#52514e', '#e3e2de'

for d in ('fonts', '/mnt/c/Windows/Fonts'):
    if os.path.isfile(os.path.join(d, 'times.ttf')):
        for name in ('times.ttf', 'timesbd.ttf', 'timesi.ttf'):
            if os.path.isfile(os.path.join(d, name)):
                font_manager.fontManager.addfont(os.path.join(d, name))
        break
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'TeX Gyre Termes', 'DejaVu Serif'],
    'font.size': 9, 'pdf.fonttype': 42,
    'axes.edgecolor': MUTED, 'axes.labelcolor': INK, 'axes.linewidth': 0.6,
    'xtick.color': MUTED, 'ytick.color': MUTED,
})
VN = FuncFormatter(lambda v, _: f'{v:g}'.replace('.', ','))


def load(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return data.get('content', data)


def style(ax):
    ax.grid(axis='y', color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)


def do_tre(repo, out):
    series = [('Đồng bộ lên', 'latency_up_randomized.json', BLUE),
              ('Lệnh xuống', 'latency_command_randomized.json', ORANGE)]
    fig, ax = plt.subplots(figsize=(4.6, 2.8))
    for label, fname, color in series:
        r = load(os.path.join(repo, 'results/report', fname))['result']
        ms = sorted(v * 1000 for v in r['latencies_sec'])
        rank = range(1, len(ms) + 1)
        ax.plot(rank, ms, color=color, lw=1.5, marker='o', ms=3.2,
                markeredgecolor='white', markeredgewidth=0.6, label=f'{label} (n = {len(ms)})')
        ax.annotate(label, (len(ms), ms[-1]), xytext=(4, -2 if color == BLUE else -11),
                    textcoords='offset points', fontsize=8, color=INK)
    ax.set_xlim(0, 37)
    ax.set_ylim(0, 1100)
    ax.set_xlabel('Thứ hạng của mẫu (từ nhỏ tới lớn)')
    ax.set_ylabel('Độ trễ (ms)')
    ax.yaxis.set_major_formatter(VN)
    ax.legend(frameon=False, fontsize=8, loc='upper left')
    style(ax)
    fig.tight_layout()
    path = os.path.join(out, 'do-tre-xep-hang.pdf')
    fig.savefig(path)
    plt.close(fig)
    print('đã ghi', path)


def ab(repo, out):
    c = load(os.path.join(repo, 'results/report/gd4cl_ab.json'))
    trials = [t for t in c['trials'] if not t.get('aborted')]
    arms = [('C', 'Bật\ncontroller', BLUE), ('B', 'Tắt\ncontroller', ORANGE)]
    fig, ax0 = plt.subplots(figsize=(3.4, 2.8))
    for ax, key, ylabel, ylim in ((ax0, 'primary', 'Tốc độ gửi trung bình của h3 (Mbps)', (0, 2.4)),):
        for i, (arm, name, color) in enumerate(arms):
            vals = [t[key] for t in trials if t['arm'] == arm]
            xs = [i + (k % 8 - 3.5) * 0.035 for k in range(len(vals))]
            ax.scatter(xs, vals, s=16, color=color, edgecolor='white', linewidth=0.6, zorder=3)
            mean = sum(vals) / len(vals)
            ax.plot([i - 0.25, i + 0.25], [mean, mean], color=INK, lw=1, zorder=4)
        ax.set_xticks([0, 1], [a[1] for a in arms])
        ax.set_xlim(-0.6, 1.6)
        ax.set_ylim(*ylim)
        ax.set_ylabel(ylabel)
        ax.yaxis.set_major_formatter(VN)
        style(ax)
    fig.subplots_adjust(left=0.2, right=0.97, top=0.95, bottom=0.2)
    path = os.path.join(out, 'ab-tung-luot.pdf')
    fig.savefig(path)
    plt.close(fig)
    print('đã ghi', path, '(%d lượt)' % len(trials))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    do_tre(sys.argv[1], sys.argv[2])
    ab(sys.argv[1], sys.argv[2])
