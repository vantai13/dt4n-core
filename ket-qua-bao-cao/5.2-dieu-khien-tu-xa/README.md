# 5.2 Điều khiển từ xa (ND2)

## Tệp kết quả

| Tệp | Dùng ở báo cáo |
|---|---|
| `latency_command_randomized.json` | độ trễ lệnh (Hình 5.1), 30 lần đo ở thời điểm ngẫu nhiên: p50 675 ms, p95 984 ms |
| `command_flow.json` | thời gian từng chặng của 60 lệnh tắt, bật link h1-s1 (chuyển lệnh, thực thi, đẩy lên Ditto mỗi bước vài ms) |
| `command_ack_timeout3.json` | hai lần gửi với thời hạn chờ 3 s: Ditto trả HTTP 408 nhưng lệnh vẫn có hiệu lực (Mục 3.3.3) |

## Chạy lại (cần testbed)

Hai launcher tự bật Ryu từ đường dẫn của máy đã thu kết quả. Trên máy khác, đặt
`export DT4N_RYU=$(which ryu-manager)` trước khi chạy. Launcher gọi `sudo -n` nên cần sudo không
hỏi mật khẩu.

```bash
sudo mn -c
PYTHONPATH="$PWD" python3 scripts/launch_ml_preflight.py    # độ trễ lệnh và phép thử HTTP 408
sudo mn -c
PYTHONPATH="$PWD" python3 scripts/run_network_suite.py      # thời gian từng chặng (command_flow)
```

Script đo: `measurements/measure_command_latency.py`, `measurements/measure_command_flow.py`,
`measurements/trace_latency.py`. Phép đo theo chặng dùng khoảng chờ cố định nên tổng thời gian
bị khóa pha; độ trễ lệnh trong báo cáo lấy từ phép đo thời điểm ngẫu nhiên.
