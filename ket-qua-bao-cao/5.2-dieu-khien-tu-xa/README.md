# 5.2 Điều khiển từ xa và độ trễ của twin

Câu hỏi của mục: gửi lệnh qua twin thì bao lâu mạng thật đổi, và làm sao biết lệnh đã có hiệu
lực. Đây là **luồng lệnh xuống**:

```
dashboard hoặc controller ──POST──▶ inbox của Thing controller trên Ditto
        ──SSE──▶ Command Agent (kiểm lệnh, chống lặp, thực thi) ──▶ Mininet
```

Muốn biết lệnh đã có hiệu lực, phải chờ trạng thái mới quay về twin qua luồng đồng bộ lên
(Mục 5.1). Vì vậy độ trễ lệnh đo được gồm **cả đường xuống lẫn đường lên**.

## Tệp kết quả

| Tệp | Trong báo cáo | Tệp gốc |
|---|---|---|
| `do-tre-lenh.json` | Mục 5.2 đoạn đầu, Hình 5.1 (đường "lệnh") | `results/report/latency_command_randomized.json` |
| `thoi-gian-tung-chang.json` | Mục 5.2: "mỗi bước chỉ mất vài mili-giây" | `results/report/command_flow.json` |
| `phan-hoi-ditto-408.json` | Mục 3.3.3: phản hồi của Ditto không xác nhận lệnh | `results/report/command_ack_timeout3.json` |

## Đọc tệp

### `do-tre-lenh.json`: con số chính thức

Mỗi lần đo: gửi `disableLink` cho link h1-s1 vào inbox, rồi hỏi Ditto mỗi 50 ms tới khi twin báo
`down`. Thời điểm gửi được chọn ngẫu nhiên như phép đo đồng bộ lên của Mục 5.1. Cấu trúc tệp giống
`do-tre-dong-bo-len.json` của Mục 5.1:

| Trường | Giá trị |
|---|---|
| `result.latencies_sec` | 30 giá trị, đơn vị giây |
| `result.min_ms`, `p50_ms`, `p95_ms`, `max_ms` | 149, 675, 984, 993 ms |
| `result.timeouts` | 0 |

### `thoi-gian-tung-chang.json`: tách độ trễ ra từng chặng

60 lệnh, xen kẽ `disableLink` và `enableLink` trên h1-s1, nằm trong `result[]`. Mỗi bên trong hệ
ghi một mốc thời gian vào nhật ký khi nó làm xong việc của mình. Mỗi chặng là hiệu của hai mốc
liền nhau:

| Mốc | Ai ghi | Lúc nào |
|---|---|---|
| CLICK | script đo, đóng vai dashboard | ngay trước khi POST lệnh vào inbox |
| RECEIVE | Command Agent | nhận được lệnh qua SSE |
| EXECUTE_DONE | Command Agent | thực thi xong, link thật đã đổi |
| STATE_DETECTED | Sync Agent | vòng đọc 1 s của nó thấy link đã đổi |
| STATE_PUSHED | Sync Agent | gửi PATCH lên Ditto thành công |
| STATE_OK | script đo | hỏi Ditto (mỗi 0,2 s) và thấy giá trị mới |

| Trường | Từ mốc, tới mốc | Là gì | Trung vị / p95 |
|---|---|---|---|
| `route_ms` | CLICK, RECEIVE | dashboard tới Ditto tới Command Agent, gộp chung vì không có mốc ở giữa | 8 / 9 ms |
| `lock_wait_ms` | | chờ khóa `net_lock` (Sync Agent có thể đang đọc mạng) | 0 / 0 ms |
| `exec_ms` | RECEIVE, EXECUTE_DONE | Command Agent kiểm lệnh và thực thi trên Mininet | 4 / 6 ms |
| `detect_ms` | EXECUTE_DONE, STATE_DETECTED | **chờ** Sync Agent tới nhịp đọc kế tiếp, không có việc gì chạy | 649 / 748 ms |
| `push_ms` | STATE_DETECTED, STATE_PUSHED | Sync Agent gửi trạng thái mới lên Ditto | 6 / 8 ms |
| `ui_ms` | STATE_PUSHED, STATE_OK | chờ script đo hỏi lại Ditto, sai số do cách đo (0-200 ms) | 113 / 201 ms |
| `total_ms` | CLICK, STATE_OK | tổng của các chặng trên | |
| `ack_ms` | CLICK, phản hồi HTTP | nhánh song song, không cộng vào tổng: Ditto trả lời "đã nhận" | 30 / 34 ms |

Ví dụ lệnh đầu tiên: 9 + 4 + 520 + 7 + 122 = 662 ms. Đường xuống thật sự (route + exec) chỉ
khoảng 12 ms. Gần như toàn bộ phần còn lại là thời gian chờ ở đường lên.

Hai giới hạn của tệp này:

- **Tổng bị khóa pha.** Trước mỗi lệnh, script bật lại link, chờ twin khớp rồi chờ thêm đúng 1 s,
  nên lệnh luôn rơi vào gần cùng một chỗ trong chu kỳ 1 s của Sync Agent. Vì thế `total_ms` dồn
  vào hai cụm hẹp, 653-665 ms và 862-877 ms, và cả lệnh tắt lẫn lệnh bật đều có ở hai cụm (tắt
  11 và 19 lệnh, bật 14 và 16 lệnh), nên tổng này không đại diện. Báo cáo chỉ
  dùng tệp này để chỉ ra route, exec, push mỗi chặng vài ms; độ trễ chính thức lấy ở `do-tre-lenh.json`.
- Không có dashboard thật: script gửi lệnh theo đúng đường của dashboard, nhưng STATE_OK là lúc
  script thấy giá trị mới, không phải lúc trình duyệt vẽ lại.

### `phan-hoi-ditto-408.json`: vì sao không dựa vào phản hồi của Ditto

Hai lần gửi `disableLink` có chờ phản hồi 3 s (lần thứ hai kèm correlation-id trong payload).

| Trường | Giá trị | Ý nghĩa |
|---|---|---|
| `http_status` | 408 | Ditto báo hết thời gian chờ phản hồi |
| `reflected_down` | `true` | dù vậy link vẫn thật sự tắt và twin đã báo `down` |
| `received_sse` | | lệnh Command Agent đã nhận qua SSE |

Kết luận: SSE không có kênh trả lời gắn với yêu cầu ban đầu, nên Ditto không bao giờ nhận được
phản hồi đúng nghĩa. Hệ thống vì thế gửi lệnh với `timeout=0` và xác nhận lệnh bằng trạng thái
quay về twin.

## Hình

Độ trễ lệnh được vẽ chung với độ trễ đồng bộ lên trong hình `do-tre-xep-hang` của Mục 5.1
(`../5.1-phan-chieu-trang-thai/hinh/`).

## Chạy lại

| Script | Đo lại | Cần |
|---|---|---|
| `do_lai_do_tre_lenh.sh` | `do-tre-lenh.json`, `phan-hoi-ditto-408.json` | testbed |
| `do_lai_thoi_gian_tung_chang.sh` | `thoi-gian-tung-chang.json`; hơn 30 phút | testbed |

```bash
ket-qua-bao-cao/5.2-dieu-khien-tu-xa/do_lai_do_tre_lenh.sh
```

Mỗi script chạy được từ bất kỳ thư mục nào. Kết quả mới ghi vào `chay-lai/<thời điểm>/` ngay trong thư mục này, cùng tên với tệp đã lưu ở trên, nên mở hai tệp cạnh nhau là so được. Kết quả đã lưu không bị đè, kể cả khi script lỗi hay bị Ctrl-C.

Script cần testbed hỏi mật khẩu sudo một lần ở đầu, tự kiểm môi trường (`scripts/kiem_tra_moi_truong.py --testbed`) và dọn Mininet trước khi chạy. Nếu `ryu-manager` không nằm trong PATH, đặt `export DT4N_RYU=/đường/dẫn/tới/ryu-manager` trước.

Hai script này là cùng lần chạy với hai script của Mục 5.1 (cùng launcher), nên chạy bên nào cũng
được và cả hai mục đều nhận kết quả mới. Nhật ký từng mốc thời gian của lệnh ở `logs/command_flow.log`.

Code đo: `measurements/measure_command_latency.py` (độ trễ lệnh),
`measurements/measure_command_flow.py` (gửi 60 lệnh), `measurements/trace_latency.py` (ghép các
mốc trong nhật ký thành từng chặng), Command Agent ở `bridge/command_agent.py`.
