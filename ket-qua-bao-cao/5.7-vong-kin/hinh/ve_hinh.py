#!/usr/bin/env python3
"""Hai hình của Mục 5.7 (vòng kín trên testbed).

ab-tung-luot      Tốc độ gửi trung bình của h3 ở từng lượt A/B. Mỗi chấm là một lượt,
                  vạch ngang là trung bình của phương án.
                  Đọc 5.7-vong-kin/ab-bao-ve.json.

dien-bien-vong-kin  Diễn biến một lượt bật controller (khối 0, lượt 1), tính từ lúc h1 bắt đầu
                  flood srv1. Dải trên là trạng thái detector công bố trên twin ở từng giây, dải
                  dưới là việc controller đang làm. Vạch dọc là lúc controller đặt giới hạn 7 Mbps
                  cho h1. Đọc nhật ký controller của lượt đó trong
                  5.7-vong-kin/du-lieu-tho/nhat-ky-controller-ab/, và mốc bắt đầu flood trong
                  ab-bao-ve.json. Script cũng in thống kê gỡ thử trên cả 16 lượt bật controller.

Ghi vào 5.7-vong-kin/hinh/, mỗi hình một bản .pdf và một bản .png. Chạy bằng ../ve_hinh.sh.
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hinh-va-bang'))
import kieu_hinh as K  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

MUC = K.KET_QUA / '5.7-vong-kin'
RA = Path(__file__).resolve().parent
NHAT_KY = MUC / 'du-lieu-tho/nhat-ky-controller-ab'
KHOI, LUOT = 0, 1          # lượt được vẽ diễn biến

TRANG_THAI = {             # giá trị trong nhật ký -> (tên trong báo cáo, màu)
    'normal': ('bình thường', '#d9e8d2'),
    'suspect': ('đáng ngờ', '#f6c87a'),
    'act': ('cần hành động', K.DO),
    'unknown': ('không rõ', '#c9bfe0'),
}
CONTROLLER = {             # chế độ của controller -> (tên trong báo cáo, màu)
    'IDLE': ('không can thiệp', '#efeeea'),
    'MITIGATING': ('giới hạn h1 ở 7 Mbps', K.XANH),
    'PROBING': ('gỡ thử giới hạn', K.CAM),
}


def ab(nd):
    luot = [t for t in nd['trials'] if not t.get('aborted')]
    nhanh = [('C', 'Bật\ncontroller', K.XANH), ('B', 'Tắt\ncontroller', K.CAM)]
    fig, ax = plt.subplots(figsize=(3.4, 2.8))
    for i, (arm, ten, mau) in enumerate(nhanh):
        v = [t['primary'] for t in luot if t['arm'] == arm]
        xs = [i + (k % 8 - 3.5) * 0.035 for k in range(len(v))]
        ax.scatter(xs, v, s=16, color=mau, edgecolor='white', linewidth=0.6, zorder=3)
        tb = sum(v) / len(v)
        ax.plot([i - 0.25, i + 0.25], [tb, tb], color=K.XAM_DAM, lw=1, zorder=4)
    ax.set_xticks([0, 1], [n[1] for n in nhanh])
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylim(0, 2.4)
    ax.set_ylabel('Tốc độ gửi trung bình của h3 (Mbps)')
    ax.yaxis.set_major_formatter(K.PHAY)
    K.truc(ax)
    fig.subplots_adjust(left=0.2, right=0.97, top=0.95, bottom=0.2)
    K.luu(fig, RA, 'ab-tung-luot')


def doan(moc, gia_tri, het):
    """Gộp chuỗi (thời điểm, giá trị) thành các đoạn liền (giá trị, bắt đầu, độ dài)."""
    out = []
    cap = list(zip(moc, gia_tri))
    for i, (t, v) in enumerate(cap):
        ket = cap[i + 1][0] if i + 1 < len(cap) else het
        if out and out[-1][0] == v:
            out[-1][2] = ket - out[-1][1]
        else:
            out.append([v, t, ket - t])
    return out


def dien_bien(nd):
    luot = next(t for t in nd['trials'] if t['block'] == KHOI and t['index'] == LUOT)
    t0 = luot['t_flood']
    nk = K.doc_jsonl(NHAT_KY / f"ab_{luot['arm']}_b{KHOI}_i{LUOT}.jsonl")
    qd = [r for r in nk if r['kind'] == 'decision']
    t = [r['t_wall'] - t0 for r in qd]
    het = 122.0
    tt = doan(t, [r['input']['state'] for r in qd], het)
    ct = doan(t, [r['cstate_after']['mode'] for r in qd], het)
    dat = [r['t_wall'] - t0 for r in nk if r['kind'] == 'inject']
    # Chỉ lấy các lần gỡ thử do hết thời gian giữ, bỏ lần gỡ khi dọn dẹp lúc hết lượt.
    go = [r['t_wall'] - t0 for r in qd if r['cstate_after']['reason'] == 'hold_expired']

    fig, ax = plt.subplots(figsize=(6.2, 2.5))
    for y, ds, bang in ((1.15, tt, TRANG_THAI), (0.0, ct, CONTROLLER)):
        for v, bd, dl in ds:
            ax.broken_barh([(bd, dl)], (y, 0.8), facecolor=bang[v][1], edgecolor='none')
    for x in dat:
        ax.axvline(x, color=K.XAM_DAM, lw=0.7, ls=(0, (2, 2)), zorder=0)
    # Thời gian giữ: từ lúc đặt giới hạn tới lúc gỡ thử kế tiếp (15 s, rồi gấp đôi mỗi lần).
    for x0 in dat:
        x1 = next((x for x in go if x > x0), None)
        if x1 is None:
            ax.text(x0 + 1, -0.32, 'giữ tiếp', ha='left', va='top', fontsize=8, color=K.XAM_DAM)
            continue
        ax.annotate('', xy=(x1, -0.22), xytext=(x0, -0.22),
                    arrowprops=dict(arrowstyle='<->', lw=0.6, color=K.XAM))
        ax.text((x0 + x1) / 2, -0.32, 'giữ %.0f s' % (x1 - x0), ha='center', va='top',
                fontsize=8, color=K.XAM_DAM)
    ax.set_yticks([0.4, 1.55], ['Controller', 'Detector'])
    ax.tick_params(axis='y', length=0)
    ax.set_xlim(-2, het)
    ax.set_ylim(-0.75, 2.05)
    ax.set_xlabel('Giây tính từ lúc h1 bắt đầu flood srv1')
    ax.xaxis.set_major_formatter(K.PHAY)
    ax.spines[['top', 'right', 'left']].set_visible(False)
    chu_giai = ([Patch(color=c, label=n) for n, c in TRANG_THAI.values()]
                + [Patch(color=c, label=n) for k, (n, c) in CONTROLLER.items() if k != 'IDLE'])
    ax.legend(handles=chu_giai, frameon=False, fontsize=8, ncol=3, loc='lower center',
              bbox_to_anchor=(0.5, 1.0), handlelength=1.2, columnspacing=1.0)
    fig.tight_layout()
    K.luu(fig, RA, 'dien-bien-vong-kin')


def thong_ke_go_thu():
    """Đếm kết cục gỡ thử và trạng thái detector lúc đang giữ trên mọi lượt bật controller."""
    ly_do, luc_giu = collections.Counter(), collections.Counter()
    tep = sorted(NHAT_KY.glob('ab_C_*.jsonl'))
    for f in tep:
        for r in K.doc_jsonl(f):
            if r['kind'] != 'decision':
                continue
            c = r['cstate_after']
            if c['reason'] in ('hold_expired', 'probe_failed_backoff', 'probe_clean'):
                ly_do[c['reason']] += 1
            if c['mode'] == 'MITIGATING' and c['reason'] == 'holding':
                luc_giu[r['input']['state']] += 1
    tong = sum(luc_giu.values())
    print('%d lượt bật controller' % len(tep))
    print('  gỡ thử: %d lần, đặt lại ngay ở giây kế tiếp: %d, gỡ thử thành công: %d' % (
        ly_do['hold_expired'], ly_do['probe_failed_backoff'], ly_do['probe_clean']))
    print('  trạng thái detector trong lúc giữ: ' + ', '.join(
        '%s %d/%d' % (TRANG_THAI[k][0], v, tong) for k, v in luc_giu.most_common()))


if __name__ == '__main__':
    nd = K.doc_json(MUC / 'ab-bao-ve.json')
    ab(nd)
    dien_bien(nd)
    thong_ke_go_thu()
