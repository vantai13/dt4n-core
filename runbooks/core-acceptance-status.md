# Nghiệm thu DT4N Core — tiếp tục từ kết quả hiện có

Kho cần chạy là `/home/ubuntu/dt4n-core`. Kho `/home/ubuntu/dt4n` giữ lịch sử và các nghiên cứu routing trước đây.

## Xem kết quả

Forward cổng 8765 trong VS Code Remote SSH rồi mở http://localhost:8765/report.html. Dashboard dùng cổng 5173. File tổng kết là `results/report/ACCEPTANCE.md`; dữ liệu có liên kết ngay trong bảng HTML.

## Bằng chứng theo tầng

| Tầng | Bằng chứng |
|---|---|
| 0: import và test | `results/report/imports.json`, `pytest.xml`, `logs/pytest.log` |
| 1: định tuyến tái lập | `results/report/routing_comparison.json`, `routing_regenerated.json`, `logs/gen_routes.log` |
| 2: Ditto, bootstrap | `logs/diagnose_audit.log`, `bootstrap_core_first.log`, `bootstrap_core_second.log`, `results/report/bootstrap_scale.json` |
| 3: mạng, traffic | `logs/acceptance_stdout.log`, `phase1_config5_stdout.log`, `snapshots_normal.jsonl`, `snapshots_flood.jsonl` |
| 4: đồng bộ | `results/report/latency_up.json`, `latency_command.json`, `command_flow.json`, `docs/phase-2/verify_report.json` |
| 5: UI, F5, điều khiển | `results/report/dashboard_smoke.json`, `dashboard_live.json`, `dashboard_last_known.json`, ảnh và `demo_video/*.webm` |
| 6: định lượng, chạy dài, bảo mật | `results/report/soak_30min.json`, `security_live.xml`, `final_summary.json`, `logs/acceptance_runtime.log` |

Không chạy thêm Mininet suite hoặc `mn -c` khi suite hiện tại còn chạy. Cả hai có thể làm gián đoạn mạng đang đo. Tiến độ nằm trong `results/report/soak_progress.json`; chỉ công nhận hoàn tất khi `complete: true` và `soak_30min.json` có `ok: true`.

## Tổng kết khi suite hoàn tất

```bash
cd /home/ubuntu/dt4n-core
python3 scripts/finish_evidence.py
python3 scripts/build_report.py
```

`finish_evidence.py` đọc các kết quả đã có và cập nhật notes phase 0–4; chạy lại không nhân đôi phần tổng kết. Script không chạy lại phép đo mạng.

Accuracy verify chỉ đo trạng thái 8 link. Bootstrap 20 client chứng minh khả năng tạo/đọc 52 Thing, chưa xác định số node tối đa ổn định. Soak giữ cả mẫu lệch lúc khôi phục link sau test bảo mật; xem từng mẫu thay vì suy ra mọi thời điểm đều đạt 100%.

Độ trễ UI đang đo từ click tới UI nhận trạng thái qua SSE. Video có trong `demo_video/`; cần xem nội dung trước khi dùng làm video bảo vệ.
