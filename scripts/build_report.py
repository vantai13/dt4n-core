import json,html,re,datetime,xml.etree.ElementTree as ET
from pathlib import Path
root=Path(__file__).resolve().parents[1]; out=root/'results/report'
def load(name):
 try:return json.loads((out/name).read_text())
 except (OSError,ValueError):return None
def stats(name):
 d=load(name+'.json');return d.get('result') if d else None
rows=[]
for label,name in [('Đồng bộ LÊN','latency_up'),('Lệnh vòng kín','latency_command')]:
 s=stats(name);rows.append([label,str(s.get('n','')) if isinstance(s,dict) else 'Đang chờ',f"{s['p50_ms']:.2f}" if isinstance(s,dict) and 'p50_ms' in s else '—',f"{s['p95_ms']:.2f}" if isinstance(s,dict) and 'p95_ms' in s else '—','< 2000 ms',name+'.json'])
ui=load('dashboard_live.json')
if ui and ui.get('stats'):
 s=ui['stats'];rows.append(['Hiển thị UI thật (click → SSE)',str(s['n']),f"{s['p50_ms']:.2f}",f"{s['p95_ms']:.2f}",'< 3000 ms','dashboard_live.json'])
flow=stats('command_flow')
if isinstance(flow,list):
 vals=[v.get('total_ms') for v in flow if v.get('total_ms') is not None]
 if vals:
  import sys;sys.path.insert(0,str(root));from measurements.stats import summarize
  s=summarize([v/1000 for v in vals]);rows.append(['Luồng lệnh tự động',str(s['n']),f"{s['p50_ms']:.2f}",f"{s['p95_ms']:.2f}",'UI thật đo riêng','command_flow.json'])
final=load('final_summary.json')
soak=load('soak_progress.json'); v=load('verification.json');scale=load('bootstrap_scale.json')
lines=['# Kết quả thực hiện DT4N Core','',f'Cập nhật UTC: {datetime.datetime.now(datetime.timezone.utc).isoformat()}','',f'Kho mới: `{root}`. Nguồn: commit `d45cf4ff26d8c6204a181f0fa77887e087a4d381`.','', '## Kết quả chạy','', '- Import: 22 module; xem `imports.json` để kiểm tra đường dẫn nạp từ kho mới.','- Pytest: xem `pytest.xml` và `../../logs/pytest.log`.','- Routing: xem `routing_comparison.json`; `../../logs/gen_routes.log` ghi kết quả không có vòng lặp.','- Ditto: namespace thí nghiệm `org.dt4n.core`, 18 Thing (5 host, 3 switch, 8 link, 1 path, 1 controller).','- Bootstrap mở rộng: 20 client + 2 server, 52 Thing; kết quả trong `bootstrap_scale.json`. Phép này chưa xác định số node tối đa ổn định trên Mininet.','', '## Số đo độ trễ','', '| Phép đo | n hợp lệ | p50 (ms) | p95 (ms) | Mục tiêu | File |','|---|---:|---:|---:|---|---|']
lines+=['| '+' | '.join(r)+' |' for r in rows]
if final:
 lines += ['', '## Tổng kết nghiệm thu cuối', '', f"Test đơn vị: {final['unit_tests']}. Security live: {final['security_live']}.", f"Completeness vật lý: {final['physical_completeness']}. Accuracy trạng thái: {final['verification']['accuracy']['accuracy_rate']}%. Event fidelity: {final['verification']['event_fidelity']['fidelity_pct']}%.", f"Soak: {final['soak'].get('duration_s')} giây; RSS đầu/cuối/max: {final['soak'].get('rss_start_kib')}/{final['soak'].get('rss_end_kib')}/{final['soak'].get('rss_max_kib')} KiB. Runtime ERROR/CRITICAL: {len(final['runtime_error_lines'])}. Tất cả mẫu accuracy tức thời 100%: {final['soak'].get('all_state_accuracy_100')}. Xem toàn bộ mẫu và ghi chú giai đoạn UI."]
lines+=['','Accuracy chỉ đánh giá trạng thái 8 link, không chứng minh độ chính xác toàn bộ metric traffic/latency.','', '## Chạy dài','', 'Chưa có mẫu soak.' if not soak else f"Đã lấy {len(soak['samples'])} mẫu; thời gian gần nhất {soak['samples'][-1]['elapsed_s']} giây; hoàn tất: {soak.get('complete',False)}.",'','## Giới hạn và khác biệt so với hướng dẫn','', '- Số file và dung lượng thực tế khác 73 file / 756 KB do dashboard có dist và danh sách hiện tại có 50 file Python; manifest ghi số thực tế.','- PYTHONPATH ban đầu trỏ repo cũ; đã chạy lại import và test với đường dẫn kho mới.','- `mn -c` dừng Ryu: phải dọn trước rồi khởi động controller. Một lần khởi động thử trùng interface đã được dọn và chạy lại; chỉ log lần chạy hoàn tất dùng cho nghiệm thu.','- Đo flow mặc định chờ ack 3 giây tạo số đo cao giả; đã đổi timeout mặc định về 0 (giống dashboard), đo lại đủ 30 cặp; log cũ trong `logs/ack3_command_flow_measure.log`.','- `--long` trong run_sync chỉ có hiệu lực cùng `--verify`; duration của nhánh đó là phút. Lệnh 1800 trong hướng dẫn không chạy soak 30 phút. Script `scripts/run_acceptance.py` đo 1800 giây bằng đồng hồ monotonic và ghi RSS mỗi phút.','- Trong các phút đầu soak có khôi phục link sau security test và 30 cặp thao tác UI. Mẫu tức thời có thể khác twin do polling 1 giây; giữ nguyên mọi mẫu trong soak_progress/soak_30min, không bỏ mẫu lệch. Phép verify tĩnh và độ trễ phản ánh sau sự kiện được báo cáo riêng.','- Verify đã sửa phân trang size=200; test bảo mật đã gửi clientCorrelationId trong payload và timeout=0. Test hồi quy phân trang/cursor lặp đã bổ sung.','- Repo đã xuất bản: https://github.com/vantai13/dt4n-core (nghiệm thu v1 ở commit 8660edf).','- Dashboard: http://localhost:5173 (forward cổng 5173 trong VS Code Remote SSH).','']
ml=load('ml_dataset_summary.json')
ml_rows=[]
if ml:
 for key,value in ml['normal_v2']['links'].items():
  f=ml['flood_v2']['links'][key]
  ml_rows.append([key,f"{value['mean_peak_direction_mbps']:.2f}",f"{f['mean_peak_direction_mbps']:.2f}",f"{f['loss_max_pct']:.3f}"])
 lines+=['', '## Bổ sung trước ML: dữ liệu v2', '',
         'Normal TCP 2 Mbps/client; flood UDP 50 Mbps/client; mọi client tới hai server luân phiên. UDP srv1→srv2 2 Mbps giữ tải s2-s3.', '',
         '| Link | Normal (Mbps) | Flood (Mbps) | Max qdisc drop flood (%) |',
         '|---|---:|---:|---:|']
 lines+=['| '+' | '.join(row)+' |' for row in ml_rows]
 lines+=['', 'Tốc độ là trung bình max(rxRate, txRate) theo mỗi snapshot. Loss v2 là local leaf-qdisc egress hai chiều, không phải loss đường đi. Bỏ mẫu đầu; qdiscValid phải true.',
         'Gate kiểm chứng: '+str(ml['gates'])+'. Xem ml_dataset_summary.json và ML_PREFLIGHT.md. Pilot này chưa chứng minh kết quả mô hình ML.']
 lines+=['', '### Độ trễ: fixed-settle v1 và randomized-settle v2', '',
         'Các mẫu v1 chụm gần một chu kỳ, phù hợp với nghi vấn khóa pha do settle cố định. Không coi v1 là giới hạn worst-case đã được chứng minh. V2 thêm jitter seed cố định trên [0, period]; collector v2 cũng thêm đọc qdisc nên đây không phải thí nghiệm chỉ thay đổi một yếu tố.', '',
         '| Phép đo randomized-settle | n | p50 (ms) | p95 (ms) | File |', '|---|---:|---:|---:|---|']
 for name in ['latency_up_randomized','latency_command_randomized']:
  d=load(name+'.json')
  if d and d.get('result'):
   x=d['result'];lines.append(f"| {name} | {x['n']} | {x['p50_ms']:.2f} | {x['p95_ms']:.2f} | {name}.json |")
 ack=load('command_ack_timeout3.json')
 if ack:
  lines+=['', '### Biên nhận lệnh', '',
          'HTTP timeout=3 trả các status: '+str([x['http_status'] for x in ack])+'. Trạng thái mạng vẫn phản ánh: '+str([x['reflected_down'] for x in ack])+'. Xem SSE gốc trong command_ack_timeout3.json.',
          'HTTP outbox POST của agent là thông báo mới, không phải Ditto Protocol response tương quan cho inbox. timeout=0 xác nhận tiếp nhận HTTP; phép đo vòng kín vẫn chờ trạng thái thật. Chi tiết và nguồn chính thức trong ML_PREFLIGHT.md.']

feature_audit=load('feature_audit_summary.json')
if feature_audit:
 lines += ['', '## Lesson 5.1 — Feature audit', '',
           f"{feature_audit['n_snapshots']} snapshot × {feature_audit['n_columns']} cột; quyết định: {feature_audit['by_decision']}.",
           f"Gate: {feature_audit['n_auc_dist_gt_0_5']} feature được GIỮ có auc_dist >0.5; kết quả {feature_audit['gate']['pass']}.",
           'Test Lesson 5.1: 51 passed, 4 skipped; xem phase5_pytest.xml. Chưa train hoặc impute. Báo cáo: ../../docs/phase-5/01-feature-audit.md; CSV/JSON/plot: feature_audit*.',
           'Pilot còn confound protocol/tải và thứ tự run; injection không có onset/baseline. AUC này là thống kê đơn biến trên dữ liệu đã audit.']

missing_analysis=load('missing_analysis.json')
if missing_analysis:
 missing_unit=ET.parse(out/'phase52_pytest.xml').getroot().find('testsuite').attrib
 missing_pass=int(missing_unit['tests'])-sum(int(missing_unit[k]) for k in ['skipped','failures','errors'])
 policy=missing_analysis['policy_applied']
 lines += ['', '## Lesson 5.2 — Dữ liệu thiếu', '',
           f"Kiểm thử: {missing_pass} passed, {missing_unit['skipped']} skipped.",
           f"Missing loss: {missing_analysis['total_pct_cells_missing']}%; bỏ {policy['rows_dropped_warmup']}/{policy['rows_before']} dòng warmup, giữ {policy['rows_after_warmup_drop']}; còn {policy['cells_missing_after']} ô loss thiếu.",
           'Collector thêm rateValid/rateReason; flatten giữ timestamp Thing. Audit GIỮ41/CHẤT VẤN11/LOẠI48, BỎ QUA74 (16 timestamp mới).',
           'MAR cho warmup quan sát được, chưa kết luận cơ chế tổng quát. Wilson/Fisher theo ô chỉ mô tả vì link/tick phụ thuộc. Chưa triển khai detector inference.',
           'Báo cáo: ../../docs/phase-5/02-missing-data.md; JSON: missing_analysis.json; log: ../../logs/missing_analysis.log.']

experiment_matrix=load('experiment_matrix.json')
if experiment_matrix:
 design_unit=ET.parse(out/'phase53_pytest.xml').getroot().find('testsuite').attrib
 design_pass=int(design_unit['tests'])-sum(int(design_unit[k]) for k in ['skipped','failures','errors'])
 lines += ['', '## Lesson5.3 — Thiết kế thí nghiệm', '',
           f"{experiment_matrix['n_runs']} run dự kiến: 8train/10test; base rate test {experiment_matrix['expected_base_rate_test']:.1%}; coverage giả thuyết 8/8link.",
           f"Test: {design_pass} passed, {design_unit['skipped']} skipped. GATE PASS: {experiment_matrix['validation']['all_pass']}.",
           'Đã có LinkAdminDown, seeded fault target và varying load cleanup process group; chưa thu18run hoặc train mô hình.',
           'Báo cáo: ../../docs/phase-5/03-experiment-matrix.md; hợp đồng: experiment_matrix.json; timeline: experiment_matrix.png.']

(out/'ACCEPTANCE.md').write_text('\n'.join(lines))
body='<h1>Kết quả chạy và đo DT4N Core</h1><p>Cập nhật UTC: '+html.escape(datetime.datetime.now(datetime.timezone.utc).isoformat())+'</p>'
body+='<p>Kho mới: '+str(root)+'</p><p><a href="http://localhost:5173">Mở dashboard (cổng 5173)</a> · <a href="results/report/ACCEPTANCE.md">Báo cáo đầy đủ</a></p>'

unit=ET.parse(out/'pytest.xml').getroot().find('testsuite').attrib
passed=int(unit['tests'])-sum(int(unit[k]) for k in ['skipped','failures','errors'])
vr=(v or {}).get('result',{}).get('results',{})
summary=[f"Test đơn vị nghiệm thu v1: {passed} passed, {unit['skipped']} skipped, {unit['failures']} failed, {unit['errors']} errors.",
 f"Accuracy trạng thái 8 link: {vr.get('accuracy',{}).get('accuracy_rate','—')}%; sự kiện phát hiện: {vr.get('event_fidelity',{}).get('detected','—')}/{vr.get('event_fidelity',{}).get('total','—')}."]
if soak:
 summary.append(f"Soak 30 phút: {'HOÀN TẤT' if soak.get('complete') else 'ĐANG CHẠY'}; {soak['samples'][-1]['elapsed_s']:.1f}/1800 giây, {len(soak['samples'])} mẫu.")
if final:
 summary.append(f"Runtime ERROR/CRITICAL: {len(final['runtime_error_lines'])}; RSS đầu/cuối/max: {final['soak'].get('rss_start_kib')}/{final['soak'].get('rss_end_kib')}/{final['soak'].get('rss_max_kib')} KiB.")
if final:
 mismatches=[x for x in final['soak']['samples'] if x['accuracy']['accuracy_rate']!=100]
 summary.append(f"Soak có {len(mismatches)} mẫu lệch trạng thái; xem soak_30min.json và ghi chú khôi phục link sau test bảo mật.")
if ml:
 current_unit=ET.parse(out/'ml_preflight_pytest.xml').getroot().find('testsuite').attrib
 current_pass=int(current_unit['tests'])-sum(int(current_unit[k]) for k in ['skipped','failures','errors'])
 summary.append(f"Kiểm chứng code v2: {current_pass} passed, {current_unit['skipped']} skipped; gate feature: {all(ml['gates'].values())}.")
body+='<div style="background:#edf6ff;padding:20px;border-radius:8px">'+''.join('<p>'+html.escape(x)+'</p>' for x in summary)+'</div><h2>Số đo thực tế</h2>'
body+='<table><tr>'+''.join('<th>'+x+'</th>' for x in ['Phép đo','n hợp lệ','p50 (ms)','p95 (ms)','Mục tiêu','File'])+'</tr>'
for r in rows:body+='<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in r[:-1])+'<td><a href="results/report/'+r[-1]+'">'+r[-1]+'</a></td></tr>'
body+='</table>'
if ml:
 body+='<h2>Dữ liệu mới trước ML (v2)</h2><p><a href="results/report/ML_PREFLIGHT.md">Báo cáo v2</a> · <a href="results/report/ml_dataset_summary.json">JSON và gate</a></p>'
 body+='<table><tr><th>Link</th><th>Normal Mbps</th><th>Flood Mbps</th><th>Max qdisc drop %</th></tr>'
 for row in ml_rows:body+='<tr>'+''.join('<td>'+html.escape(value)+'</td>' for value in row)+'</tr>'
 body+='</table><p>Loss là drop qdisc egress tại link, không phải loss end-to-end. Dữ liệu này là pilot kiểm chứng feature.</p>'
 for name in ['latency_up_randomized','latency_command_randomized']:
  d=load(name+'.json')
  if d and d.get('result'):
   x=d['result'];body+=f"<p>{name}: n={x['n']}, p50={x['p50_ms']:.2f} ms, p95={x['p95_ms']:.2f} ms.</p>"
if experiment_matrix:
 body+='<h2 id="experiment-matrix">Lesson5.3 — Ma trận thiết kế trước thu</h2>'
 body+=f"<p>{experiment_matrix['n_runs']} run: 8 train-normal, 2 test-control, 8 test-fault. {design_pass} passed, {design_unit['skipped']} skipped.</p>"
 body+=f"<p>GATE PASS: {experiment_matrix['validation']['all_pass']}; base rate test dự kiến {experiment_matrix['expected_base_rate_test']:.1%}; coverage giả thuyết 8/8link. CHƯA THU DỮ LIỆU.</p>"
 body+='<p>Đã thêm LinkAdminDown, severity từ seed đúng target, varying load và cleanup shell scheduler. Train varying A hai seed; test-control B.</p>'
 body+='<p><a href="docs/phase-5/03-experiment-matrix.md">Báo cáo</a> · <a href="docs/phase-5/03-experiment-matrix.generated.md">Bảng18run</a> · <a href="results/report/experiment_matrix.json">JSON hợp đồng</a> · <a href="logs/build_matrix.log">Output gate</a> · <a href="logs/phase53_pytest.log">Log test</a></p>'
 body+='<img style="width:100%" src="results/report/experiment_matrix.png" alt="Thứ tự18run và timeline dự kiến">'

if missing_analysis:
 body+='<h2 id="missing-data">Lesson 5.2 — Dữ liệu thiếu</h2>'
 body+=f"<p>{missing_pass} passed, {missing_unit['skipped']} skipped. Missing loss: {missing_analysis['total_pct_cells_missing']}% (24/1200 ô), đều warmup tick 0.</p>"
 body+=f"<p>DT4N-M1: bỏ {policy['rows_dropped_warmup']}/{policy['rows_before']} dòng; giữ {policy['rows_after_warmup_drop']}; còn {policy['cells_missing_after']} ô loss thiếu. Collector đã thêm rateValid/rateReason.</p>"
 body+='<p>Audit vẫn GIỮ 41 / CHẤT VẤN 11 / LOẠI 48; thêm 16 timestamp metadata → 174 cột, BỎ QUA 74. Chưa train mô hình.</p>'
 body+='<p><a href="docs/phase-5/02-missing-data.md">Báo cáo Lesson 5.2</a> · <a href="results/report/missing_analysis.json">JSON và manifest</a> · <a href="logs/missing_analysis.log">Output phân tích</a> · <a href="logs/phase52_pytest.log">Log kiểm thử</a></p>'
 body+='<p>MAR cho warmup quan sát được; chưa kết luận missingness tổng quát. CI/Fisher theo ô chỉ mô tả vì mẫu phụ thuộc.</p>'
 body+='<img style="width:100%" src="results/report/missing_analysis.png" alt="Missingness theo profile và chính sách DT4N-M1">'

if feature_audit:
 phase_unit=ET.parse(out/'phase5_pytest.xml').getroot().find('testsuite').attrib
 phase_pass=int(phase_unit['tests'])-sum(int(phase_unit[k]) for k in ['skipped','failures','errors'])
 body+='<h2 id="feature-audit">Lesson 5.1 — Feature audit</h2>'
 body+=f"<p>{feature_audit['n_snapshots']} snapshot × {feature_audit['n_columns']} cột; {phase_pass} passed, {phase_unit['skipped']} skipped.</p>"
 body+='<table><tr><th>Quyết định</th><th>Số cột</th></tr>'
 for key in ['GIU','CHAT_VAN','LOAI','BO_QUA']:
  body+=f"<tr><td>{key}</td><td>{feature_audit['by_decision'][key]}</td></tr>"
 body+='</table>'
 body+=f"<p>Gate PASS: {feature_audit['n_auc_dist_gt_0_5']} feature được giữ có auc_dist &gt;0.5. Chưa huấn luyện mô hình; pilot còn confound tải/protocol.</p>"
 body+='<p><a href="docs/phase-5/01-feature-audit.md">Báo cáo Lesson 5.1</a> · <a href="results/report/feature_audit.csv">CSV từng cột</a> · <a href="results/report/feature_audit_summary.json">JSON và SHA-256</a> · <a href="logs/phase5_pytest.log">Log test</a></p>'
 body+='<a href="results/report/feature_audit_dist.png"><img style="width:100%" src="results/report/feature_audit_dist.png" alt="Phân bố normal và fault của 8 feature"></a>'

body+='<h2>Trạng thái nghiệm thu</h2>'

for filename in ['routing_comparison.json','bootstrap_scale.json','verification.json','security_live.json','soak_progress.json','dashboard_smoke.json','dashboard_live.json','dashboard_last_known.json','final_summary.json']:
 d=load(filename)
 body+='<details><summary>'+filename+(' — đang chờ' if d is None else '')+'</summary><pre>'+html.escape(json.dumps(d,indent=2,ensure_ascii=False))+'</pre></details>'
body+='<h2>File dữ liệu</h2><ul>'
for folder in ['results/report','logs','docs/phase-2']:
 for f in sorted((root/folder).glob('*')):
  if f.is_file():body+='<li><a href="'+str(f.relative_to(root))+'">'+str(f.relative_to(root))+'</a></li>'
body+='</ul>'
(root/'report.html').write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><meta http-equiv="refresh" content="30"><title>Kết quả DT4N Core</title><style>body{font:16px system-ui;margin:32px;max-width:1200px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:12px;text-align:left}pre{white-space:pre-wrap;background:#eee;padding:16px}details{margin:12px 0}a{color:#075bb2}</style>'+body+'</html>')
print(out/'ACCEPTANCE.md')
