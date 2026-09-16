"""Render the measured Phase 5 dataset receipt; does not load or fit a detector."""
import argparse
import html
import json
from pathlib import Path
from ml import campaign as C


def build(root):
    report = root / 'results/report'
    m = json.loads((report/'ml_dataset_split_manifest.json').read_text())
    p = json.loads((report/'ground_truth.json').read_text())['receipt']
    timing = ''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in
                      (rid, x['earliest_channel'], x['onset_delay_ticks'],
                       x['witness'], x['witness_onset_delay_ticks'], x['recovery_delay_ticks']))+'</tr>'
                     for rid,x in p['signal_timing'].items())
    missing = m['unjudgeable_test_ticks']
    envelope_info = ''
    if 'envelope' in m:
        envelope_info = f"<h2>Envelope — cuối Phase 5</h2><div class='metrics'>{len(m['envelope'])} cột envelope · {m['n_envelope_only_columns']} riêng · {m['n_envelope_if_overlap']} giao IF<br>K={m['envelope_threshold']['K']} · k_train_mean={m['envelope_threshold']['k_train_mean']} · {m['n_dead_features']} constant khác</div><p>Bounds fit trên 472 dòng train. K=0 theo định nghĩa; FPR ngoài mẫu chưa đo. Synthetic sklearn1.8.0: constant 0/200 cây split, score bất biến; không fit detector chiến dịch.</p>"
    text = f'''<!doctype html><html lang="vi"><meta charset="utf-8"><title>DT4N Lesson 5.6</title>
<style>body{{font:16px system-ui;max-width:1250px;margin:30px auto;color:#153044}}table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;border:1px solid #ccd}}.metrics{{padding:22px;background:#e8f5ed;font-size:22px}}img{{width:100%}}</style>
<h1>Lesson 5.6 — Dataset DT4N-D1</h1><div class="metrics">{m['shape']['n_features']} feature · {m['shape']['n_train_rows']} train · {m['shape']['n_test_rows']} test<br>
Base rate chính: 160/590 = 27,12% · Độ nhạy: 144/558 = 25,81%<br>Onset sớm nhất: 0 tick ở cả 8 run lỗi · Grace onset2/recovery2</div>
<p>Missing feature: {missing['total']} tick — {missing['with_fault']} lỗi, {missing['with_normal']} bình thường. Delta lan NaN sang tick kế tiếp; giữ toàn bộ test. Recall ceiling theo chính sách unknown: 95% (chưa chạy detector).</p>
<p>Chọn feature từ train, không dùng audit có nhãn test. Fit thống kê trên train; chia theo run; delta/rolling trong từng run. 4 nhóm cấu hình normal cho CV ở Phase 6.</p>
{envelope_info}<table><tr><th>Run</th><th>Kênh sớm nhất</th><th>Onset sớm</th><th>Chứng nhân mạnh nhất</th><th>Onset chứng nhân</th><th>Recovery chứng nhân</th></tr>{timing}</table>
<p>Degrade s2–s3: txRate lệch ngay tick21; lossPct mạnh nhất lệch tick31. Hai phép đo khác nhau; bản cũ được lưu để đối chiếu.</p>
<img src="label_overlay.png"><p><a href="ml_dataset_split_manifest.json">Manifest đo</a> · <a href="ground_truth.json">Onset từng kênh và13gate</a> · <a href="../../docs/phase-5/06-dataset-card.md">Dataset card</a></p></html>'''
    target = report / ('phase56b_results.html' if 'envelope' in m else 'phase56_results.html')
    target.write_text(text)
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=C.ROOT)
    build(parser.parse_args().root.resolve())
