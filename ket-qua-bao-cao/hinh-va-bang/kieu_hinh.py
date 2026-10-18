"""Kiểu vẽ dùng chung cho mọi hình của báo cáo.

Script vẽ của từng mục (ket-qua-bao-cao/<mục>/hinh/ve_hinh.py) nạp tệp này để mọi hình có cùng
phông, màu, cỡ chữ và dấu phẩy thập phân. Mỗi hình được ghi hai bản cạnh nhau:
  .pdf  dạng vector, để chèn vào LaTeX
  .png  để xem nhanh trên GitHub hoặc trong trình xem ảnh
"""
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

GOC = Path(__file__).resolve().parents[2]          # gốc repo dt4n-core
KET_QUA = GOC / 'ket-qua-bao-cao'

# Bảng màu. Hai màu đầu dễ phân biệt cả với người mù màu đỏ-lục.
XANH, CAM = '#2a78d6', '#eb6834'
XAM_DAM, XAM, LUOI = '#0b0b0b', '#52514e', '#e3e2de'
XANH_LA, DO, TIM = '#3a9a5b', '#c8443a', '#8a63c9'

for thu_muc in (GOC / 'fonts', Path('/mnt/c/Windows/Fonts')):
    if (thu_muc / 'times.ttf').is_file():
        for ten in ('times.ttf', 'timesbd.ttf', 'timesi.ttf'):
            if (thu_muc / ten).is_file():
                font_manager.fontManager.addfont(str(thu_muc / ten))
        break
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'TeX Gyre Termes', 'Liberation Serif', 'DejaVu Serif'],
    'font.size': 9, 'pdf.fonttype': 42,
    # Ký hiệu toán ($e$, $r_{\max}$) dùng kiểu chữ giống Times, khớp với công thức trong báo cáo.
    'mathtext.fontset': 'stix',
    'axes.edgecolor': XAM, 'axes.labelcolor': XAM_DAM, 'axes.linewidth': 0.6,
    'xtick.color': XAM, 'ytick.color': XAM,
})

# Dấu phẩy thập phân như trong thân báo cáo: 0,5 thay vì 0.5.
PHAY = FuncFormatter(lambda v, _: f'{v:g}'.replace('.', ','))


def doc_json(path):
    """Đọc tệp kết quả. Nhiều tệp bọc nội dung trong khóa 'content'."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return data.get('content', data) if isinstance(data, dict) else data


def doc_jsonl(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def truc(ax, luoi='y'):
    """Kiểu trục chung: lưới nhạt, bỏ khung trên và phải."""
    if luoi:
        ax.grid(axis=luoi, color=LUOI, lw=0.5)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)


def luu(fig, thu_muc, ten):
    """Ghi <ten>.pdf và <ten>.png vào thu_muc rồi đóng hình."""
    os.makedirs(thu_muc, exist_ok=True)
    for duoi, them in (('pdf', {}), ('png', {'dpi': 200})):
        path = os.path.join(thu_muc, f'{ten}.{duoi}')
        fig.savefig(path, **them)
        print('đã ghi', os.path.relpath(path, GOC))
    plt.close(fig)
