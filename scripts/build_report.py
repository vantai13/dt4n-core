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
lines+=['','Accuracy chỉ đánh giá trạng thái 8 link, không chứng minh độ chính xác toàn bộ metric traffic/latency.','', '## Chạy dài','', 'Chưa có mẫu soak.' if not soak else f"Đã lấy {len(soak['samples'])} mẫu; thời gian gần nhất {soak['samples'][-1]['elapsed_s']} giây; hoàn tất: {soak.get('complete',False)}.",'','## Giới hạn và khác biệt so với hướng dẫn','', '- Số file và dung lượng thực tế khác 73 file / 756 KB do dashboard có dist và danh sách hiện tại có 50 file Python; manifest ghi số thực tế.','- PYTHONPATH ban đầu trỏ repo cũ; đã chạy lại import và test với đường dẫn kho mới.','- `mn -c` dừng Ryu: phải dọn trước rồi khởi động controller. Một lần khởi động thử trùng interface đã được dọn và chạy lại; chỉ log lần chạy hoàn tất dùng cho nghiệm thu.','- Đo flow mặc định chờ ack 3 giây tạo số đo cao giả; đã đổi timeout mặc định về 0 (giống dashboard), đo lại đủ 30 cặp; log cũ trong `logs/ack3_command_flow_measure.log`.','- `--long` trong run_sync chỉ có hiệu lực cùng `--verify`; duration của nhánh đó là phút. Lệnh 1800 trong hướng dẫn không chạy soak 30 phút. Script `scripts/run_acceptance.py` đo 1800 giây bằng đồng hồ monotonic và ghi RSS mỗi phút.','- Trong các phút đầu soak có khôi phục link sau security test và 30 cặp thao tác UI. Mẫu tức thời có thể khác twin do polling 1 giây; giữ nguyên mọi mẫu trong soak_progress/soak_30min, không bỏ mẫu lệch. Phép verify tĩnh và độ trễ phản ánh sau sự kiện được báo cáo riêng.','- Verify đã sửa phân trang size=200; test bảo mật đã gửi clientCorrelationId trong payload và timeout=0. Test hồi quy phân trang/cursor lặp đã bổ sung.','- Chưa đẩy GitHub: truy cập `vantai13/dt4n-core` báo Repository not found.','- Dashboard: http://localhost:5173 (forward cổng 5173 trong VS Code Remote SSH).','']
(out/'ACCEPTANCE.md').write_text('\n'.join(lines))
body='<h1>Kết quả chạy và đo DT4N Core</h1><p>Cập nhật UTC: '+html.escape(datetime.datetime.now(datetime.timezone.utc).isoformat())+'</p>'
body+='<p>Kho mới: '+str(root)+'</p><p><a href="http://localhost:5173">Mở dashboard (cổng 5173)</a> · <a href="results/report/ACCEPTANCE.md">Báo cáo đầy đủ</a></p>'

unit=ET.parse(out/'pytest.xml').getroot().find('testsuite').attrib
passed=int(unit['tests'])-sum(int(unit[k]) for k in ['skipped','failures','errors'])
vr=(v or {}).get('result',{}).get('results',{})
summary=[f"Test đơn vị: {passed} passed, {unit['skipped']} skipped, {unit['failures']} failed, {unit['errors']} errors.",
 f"Accuracy trạng thái 8 link: {vr.get('accuracy',{}).get('accuracy_rate','—')}%; sự kiện phát hiện: {vr.get('event_fidelity',{}).get('detected','—')}/{vr.get('event_fidelity',{}).get('total','—')}."]
if soak:
 summary.append(f"Soak 30 phút: {'HOÀN TẤT' if soak.get('complete') else 'ĐANG CHẠY'}; {soak['samples'][-1]['elapsed_s']:.1f}/1800 giây, {len(soak['samples'])} mẫu.")
if final:
 summary.append(f"Runtime ERROR/CRITICAL: {len(final['runtime_error_lines'])}; RSS đầu/cuối/max: {final['soak'].get('rss_start_kib')}/{final['soak'].get('rss_end_kib')}/{final['soak'].get('rss_max_kib')} KiB.")
if final:
 mismatches=[x for x in final['soak']['samples'] if x['accuracy']['accuracy_rate']!=100]
 summary.append(f"Soak có {len(mismatches)} mẫu lệch trạng thái; xem soak_30min.json và ghi chú khôi phục link sau test bảo mật.")
body+='<div style="background:#edf6ff;padding:20px;border-radius:8px">'+''.join('<p>'+html.escape(x)+'</p>' for x in summary)+'</div><h2>Số đo thực tế</h2>'
body+='<table><tr>'+''.join('<th>'+x+'</th>' for x in ['Phép đo','n hợp lệ','p50 (ms)','p95 (ms)','Mục tiêu','File'])+'</tr>'
for r in rows:body+='<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in r[:-1])+'<td><a href="results/report/'+r[-1]+'">'+r[-1]+'</a></td></tr>'
body+='</table><h2>Trạng thái nghiệm thu</h2>'
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
