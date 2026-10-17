#!/usr/bin/env python3
"""Sinh bảng LaTeX từ file kết quả kiểm mù what-if (blind_result.json).

Vì sao có script này: số trong báo cáo không được gõ tay. Script đọc
thẳng file kết quả trong repo và ghi ra tables/whatif-blind.tex, kèm
mã băm của file nguồn ở đầu bảng để biết bảng sinh từ phiên bản nào.

Cách chạy (từ thư mục báo cáo, hoặc `make bang`, xem Makefile):
    python3 scripts/receipt_to_table.py \
        ~/dt4n-core/results/gd3/blind_result.json tables/whatif-blind.tex
"""
import hashlib
import json
import sys
from pathlib import Path

LATEX_SPECIAL = {
    '\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
    '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}',
    '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
}


def tex_escape(text: str) -> str:
    """Escape 10 ký tự đặc biệt, rồi đổi '->' thành mũi tên."""
    out = ''.join(LATEX_SPECIAL.get(ch, ch) for ch in text)
    return out.replace('->', r'$\to$')


def vn_number(x: float, digits: int = 2) -> str:
    """0.5 -> '0,50' (dấu thập phân kiểu Việt Nam)."""
    return f'{x:.{digits}f}'.replace('.', ',')


def build_rows(result: dict) -> list:
    rows = []
    for case_id, case in result['cases'].items():
        rows.append(r'\midrule')
        rows.append(r'\multicolumn{6}{@{}l}{\textit{%s (lần đo %d)}} \\'
                    % (tex_escape(case['title']), case['try']))
        for item in case['items']:
            for key in ('id', 'what', 'pred', 'meas', 'tol', 'verdict'):
                if key not in item:
                    raise KeyError(f'{case_id}/{item.get("id")}: thiếu trường {key}')
            what = item['what']
            if item.get('control'):
                what = what.replace('ĐỐI CHỨNG: ', '')
                what = r'\textit{Đối chứng:} ' + tex_escape(what)
            else:
                what = tex_escape(what)
            rows.append(' & '.join([
                item['id'], what,
                vn_number(item['pred']), vn_number(item['meas']),
                r'$\pm$' + vn_number(item['tol']),
                tex_escape(item['verdict'].lower()),   # 'ĐẠT' -> 'đạt', như văn bản
            ]) + r' \\')
    return rows


def main(src: str, dst: str) -> None:
    raw = Path(src).read_bytes()
    result = json.loads(raw)
    sha = hashlib.sha256(raw).hexdigest()
    s = result['summary']
    # Ghi đường dẫn tính từ gốc repo (results/...), không phụ thuộc máy.
    label = src[src.find('results/'):] if 'results/' in src else src
    lines = [
        '% TỰ SINH bởi scripts/receipt_to_table.py — KHÔNG sửa tay.',
        f'% Nguồn (trong repo dt4n-core): {label}',
        f'% sha256 nguồn: {sha}',
        f'% Dự đoán: {result.get("predictions_commit", "?")}',
        r'\begin{tabularx}{\textwidth}{@{}lXrrrl@{}}',
        r'\toprule',
        r'ID & Đại lượng & Dự đoán & Đo & Ngưỡng & Kết quả \\',
        *build_rows(result),
        r'\midrule',
        r'\multicolumn{6}{@{}l}{Tổng: %d/%d dự đoán đạt} \\' % (s['pass'], s['n']),
        r'\bottomrule',
        r'\end{tabularx}',
    ]
    Path(dst).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'đã ghi {dst} ({s["pass"]}/{s["n"]} đạt, nguồn sha256 {sha[:12]})')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
