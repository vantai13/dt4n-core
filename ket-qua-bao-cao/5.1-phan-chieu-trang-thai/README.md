# 5.1 Phản chiếu trạng thái mạng (ND1)

## Tệp kết quả

| Tệp | Dùng ở báo cáo |
|---|---|
| `verification.json` | Bảng 5.1: đủ 5 host, 3 switch, 8 link; 8/8 link khớp; 20/20 lần tắt link h1-s1 được phản ánh trong 10 s |
| `latency_up_randomized.json` | độ trễ đồng bộ lên, 30 lần đo ở thời điểm ngẫu nhiên: p50 682 ms, p95 1017 ms, lớn nhất 1019 ms; Hình 5.1 |
| `soak_30min.json` | chạy liên tục 30 phút: 30/31 lần kiểm khớp, bộ nhớ tăng 212 KiB |

## Chạy lại (cần testbed)

Hai launcher tự bật Ryu từ đường dẫn của máy đã thu kết quả. Trên máy khác, đặt
`export DT4N_RYU=$(which ryu-manager)` trước khi chạy. Launcher gọi `sudo -n` nên cần sudo không
hỏi mật khẩu.

Độ trễ đồng bộ lên (cùng lần chạy với độ trễ lệnh ở Mục 5.2):

```bash
sudo mn -c
PYTHONPATH="$PWD" python3 scripts/launch_ml_preflight.py    # tự bật Ryu, đo 30 lần mỗi loại
python3 scripts/analyze_ml_preflight.py
```

Đối chiếu thực thể, 20 lần tắt link và chạy liên tục 30 phút (bộ nghiệm thu mạng):

```bash
sudo mn -c
PYTHONPATH="$PWD" python3 scripts/run_network_suite.py
```

Định nghĩa phép đo ở Mục 4.4.1 của báo cáo; script đo nằm ở `measurements/measure_latency.py` và
`bridge/verify.py`.
