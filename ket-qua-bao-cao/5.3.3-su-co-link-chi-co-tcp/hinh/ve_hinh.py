#!/usr/bin/env python3
"""Hình diễn biến của sự cố giảm băng thông ở hệ số tải 1,25 (Mục 5.3.3).

Hình có bốn ô dùng chung trục thời gian, vùng tô xám là lúc sự cố đang diễn ra (giây 20-40).

  (a), (b)  Run chẩn đoán hàng đợi trên s1-s2 (du-lieu-tho/degrade_sensor_s1-s2_f0.8275_offoff_rev40_
            20260917T074237Z). (a) là số gói đang nằm trong hàng đợi của s1 hướng về s2, đọc từ
            qdisc netem mỗi giây, kèm vạch giới hạn 1000 gói và lúc gói đầu tiên bị bỏ.
            (b) là độ trễ khứ hồi của ping từ h1 tới srv1, đo 5 lần mỗi giây.
  (c), (d)  Hai run giảm băng thông ở hệ số tải 1,25 của tập kiểm tra độc lập, một trên s1-s2 và
            một trên s2-s3 (5.3-phat-hien-bat-thuong/du-lieu/tap-kiem-tra-doc-lap/). (c) là điểm
            excess e của kênh envelope so với ngưỡng E, (d) là residual lớn nhất r_max so với ngưỡng
            R. Cả hai được tính bằng chính code của detector 2.1 (ml/serve_fast.py), giống
            scripts/xuat_csv_du_lieu.py.

Run chẩn đoán và run của tập kiểm tra độc lập là hai lần chạy khác nhau, cùng giảm băng thông
s1-s2 xuống khoảng 0,83 lần mức gốc. Ghi vào 5.3.3-su-co-link-chi-co-tcp/hinh/dien-bien-s1-s2
.pdf và .png. Chạy bằng ../ve_hinh.sh.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hinh-va-bang'))
import kieu_hinh as K  # noqa: E402

sys.path.insert(0, str(K.GOC))
import matplotlib.pyplot as plt  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402
from ml.serve_fast import FastOnlineScorer  # noqa: E402

MUC = K.KET_QUA / '5.3.3-su-co-link-chi-co-tcp'
RA = Path(__file__).resolve().parent
CHAN_DOAN = MUC / 'du-lieu-tho/degrade_sensor_s1-s2_f0.8275_offoff_rev40_20260917T074237Z'
KIEM_TRA = K.KET_QUA / '5.3-phat-hien-bat-thuong/du-lieu/tap-kiem-tra-doc-lap'
RUN = [('s1-s2', 'RD-degrade-s1-s2-rho125-s5103-r1', K.XANH),
       ('s2-s3', 'RD-degrade-s2-s3-rho125-s5108-r1', K.CAM)]


def chan_doan():
    """(giây, gói trong hàng đợi, giây có gói bị bỏ đầu tiên) và (giây, RTT ms) của run chẩn đoán."""
    mau = K.doc_jsonl(Path(str(CHAN_DOAN) + '.jsonl'))
    goc = mau[0]['t_wall'] - mau[0]['t_rel']
    giay, hang_doi, bo_dau = [], [], None
    bo_truoc = None
    for m in mau:
        netem = next(q for q in m['interfaces']['upstream_egress']['tc_qdisc'] if q['kind'] == 'netem')
        giay.append(m['t_rel'])
        hang_doi.append(netem['qlen'])
        if bo_truoc is not None and netem['drops'] > bo_truoc and bo_dau is None:
            bo_dau = m['t_rel']
        bo_truoc = netem['drops']
    rtt = []
    for dong in Path(str(CHAN_DOAN) + '.ping.log').read_text().splitlines():
        k = re.match(r'\[(\d+\.\d+)\].*time=([\d.]+) ms', dong)
        if k:
            rtt.append((float(k.group(1)) - goc, float(k.group(2))))
    return giay, hang_doi, bo_dau, rtt


def detector():
    ban = DetectorRelease.load(K.GOC / 'models/detector-release-2.1.0.json')
    cham = FastOnlineScorer(ban.model, expected_collector_version=ban.content['collector_version'],
                            conservation=ban.conservation, conservation_mode='active')
    E = float(ban.model.thresholds['primary']['E'])
    R = float(ban.conservation.threshold)
    chuoi = {}
    for link, run, _ in RUN:
        giay, ex, rr = [], [], []
        for snap in K.doc_jsonl(KIEM_TRA / f'{run}.jsonl'):
            row, values, _ = cham._values(snap)
            _, excess, ok = cham._family(values, 'primary')
            ok_r, r_max, _, _ = cham._conservation(row)
            # Giây có dữ liệu không hợp lệ (ví dụ ngay sau khi đổi băng thông, bộ đếm hàng đợi vừa
            # bị đặt lại) bị detector bỏ qua, nên cũng không vẽ.
            giay.append(int(snap['tick']))
            ex.append(excess if ok else float('nan'))
            rr.append(r_max if ok and ok_r else float('nan'))
        chuoi[link] = (giay, ex, rr)
    return E, R, chuoi


def main():
    giay, hang_doi, bo_dau, rtt = chan_doan()
    E, R, chuoi = detector()
    fig, (a, b, c, d) = plt.subplots(4, 1, figsize=(6.0, 7.0), sharex=True,
                                     gridspec_kw={'height_ratios': [1, 0.8, 1, 1]})
    for ax in (a, b, c, d):
        ax.axvspan(20, 40, color='#e9e8e4', zorder=0)
        K.truc(ax)
        ax.yaxis.set_major_formatter(K.PHAY)

    a.plot(giay, hang_doi, color=K.XANH, lw=1.4)
    a.axhline(1000, color=K.XAM, lw=0.8, ls='--')
    a.text(0.5, 1000, 'giới hạn 1000 gói', va='bottom', fontsize=8, color=K.XAM_DAM)
    if bo_dau is not None:
        a.axvline(bo_dau, color=K.DO, lw=0.9)
        a.text(bo_dau - 0.4, 500, 'gói đầu tiên\nbị bỏ', ha='right', fontsize=8, color=K.DO)
    a.set_ylabel('Số gói')
    a.set_ylim(0, 1150)
    a.set_title('(a) Số gói trong hàng đợi của s1 hướng về s2, run chẩn đoán', loc='left', fontsize=9)

    b.plot([x for x, _ in rtt], [v / 1000 for _, v in rtt], color=K.TIM, lw=1.0)
    b.set_ylabel('RTT (s)')
    b.set_title('(b) Độ trễ khứ hồi của ping từ h1 tới srv1, cùng run chẩn đoán', loc='left', fontsize=9)
    b.set_ylim(bottom=0)

    for link, _, mau in RUN:
        g, ex, _ = chuoi[link]
        c.plot(g, ex, color=mau, lw=1.4, label=f'sự cố trên {link}')
    c.axhline(E, color=K.XAM_DAM, lw=0.8, ls='--')
    c.text(0.5, E, f'ngưỡng $E$ ≈ {E:.2f}'.replace('.', ','), va='bottom', fontsize=8, color=K.XAM_DAM)
    c.set_ylabel('$e$')
    c.annotate('pha phục hồi', xy=(42, 22), xytext=(47, 15), fontsize=8, color=K.XAM_DAM,
               arrowprops=dict(arrowstyle='->', lw=0.6, color=K.XAM))
    c.legend(frameon=False, fontsize=8, loc='upper left', bbox_to_anchor=(0.0, 0.92))
    c.set_title('(c) Điểm excess, hai run của tập kiểm tra độc lập ở hệ số tải 1,25', loc='left', fontsize=9)

    for link, _, mau in RUN:
        g, _, rr = chuoi[link]
        d.plot(g, rr, color=mau, lw=1.4)
    d.axhline(R, color=K.XAM_DAM, lw=0.8, ls='--')
    d.text(0.5, R, f'ngưỡng $R$ ≈ {R:.3f}'.replace('.', ','), va='bottom', fontsize=8, color=K.XAM_DAM)
    d.set_ylabel(r'$r_{\max}$')
    d.set_title('(d) Residual lớn nhất, cùng hai run', loc='left', fontsize=9)
    d.set_xlabel('Giây trong run (sự cố từ giây 20 tới giây 40)')
    d.set_xlim(0, 60)
    fig.align_ylabels()
    fig.tight_layout()
    K.luu(fig, RA, 'dien-bien-s1-s2')
    print('lúc gói đầu tiên bị bỏ: giây %.1f, hàng đợi lớn nhất %d gói, RTT lớn nhất %.2f s' % (
        bo_dau, max(hang_doi), max(v for _, v in rtt) / 1000))
    for link in chuoi:
        g, ex, rr = chuoi[link]
        trong = [i for i, x in enumerate(g) if 21 <= x <= 40]
        tu = next((g[i] for i in trong if all(rr[j] > R for j in trong if g[j] >= g[i] and rr[j] == rr[j])), None)
        print('%s: excess lớn nhất trong sự cố %.2f (E %.2f), residual > R liên tục từ giây: %s' % (
            link, max((ex[i] for i in trong if ex[i] == ex[i]), default=float('nan')), E,
            tu if tu is not None else 'không có'))
    tre = [v for x, v in rtt if 30 <= x <= 40]
    print('RTT trung vị giây 30-40: %.2f s' % (sorted(tre)[len(tre) // 2] / 1000))


if __name__ == '__main__':
    main()
