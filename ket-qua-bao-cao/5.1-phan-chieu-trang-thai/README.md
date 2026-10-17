# 5.1 Phản chiếu trạng thái mạng (ND1)

Câu hỏi của mục: twin có đủ, đúng và kịp so với testbed không. Mọi phép đo ở đây đi theo **luồng
đồng bộ lên**: Mininet đổi trạng thái, Sync Agent đọc mạng mỗi 1 s và đẩy phần thay đổi lên Ditto.

## Tệp kết quả

| Tệp | Trong báo cáo | Tệp gốc |
|---|---|---|
| `doi-chieu-va-20-lan-tat-link.json` | Bảng 5.1, ba dòng Đủ, Đúng, Bắt được sự kiện | `results/report/verification.json` |
| `do-tre-dong-bo-len.json` | Bảng 5.1 dòng Kịp thời, Hình 5.1 (đường "đồng bộ lên") | `results/report/latency_up_randomized.json` |
| `chay-lien-tuc-30-phut.json` | Bảng 5.1 dòng Bền, đoạn sau bảng | `results/report/soak_30min.json` |

## Đọc tệp

### `doi-chieu-va-20-lan-tat-link.json`

Ba phép kiểm chạy liên tiếp trên cùng một testbed, nằm dưới `result.results`:

| Trường | Ý nghĩa | Giá trị |
|---|---|---|
| `completeness.hosts`, `.switches`, `.links` | số thực thể có trên Ditto so với Mininet (`expected`, `actual`, `missing`, `extra`) | 5/5, 3/3, 8/8 |
| `accuracy` | so trạng thái bật, tắt của từng link giữa Mininet và twin | `matched` 8 / `checked` 8 |
| `event_fidelity` | tắt link h1-s1 20 lần, mỗi lần chờ tối đa 10 s để twin báo `down` | `detected` 20 / `total` 20 |
| `event_fidelity.log[]` | từng lần tắt: `latency_s` là thời gian tới khi twin báo `down` | |

Bỏ qua mục `freshness`: nó chỉ ghi chú rằng độ trễ được đo riêng, ở tệp kế tiếp.

### `do-tre-dong-bo-len.json`

Mỗi lần đo: gọi lệnh tắt link h1-s1 **trực tiếp trên Mininet**, rồi một script hỏi Ditto mỗi
50 ms để biết lúc twin báo `down`. Trước mỗi lần, link được bật lại và hệ chờ 2 s cộng một khoảng
ngẫu nhiên 0-1 s, để thời điểm tắt rơi ngẫu nhiên so với chu kỳ đọc 1 s
(`result.phase_mode` = `randomized_settle`).

| Trường | Ý nghĩa |
|---|---|
| `result.latencies_sec` | 30 giá trị đo, đơn vị giây, theo thứ tự đo |
| `result.min_ms`, `p50_ms`, `p95_ms`, `max_ms` | 179, 682, 1017, 1019 ms |
| `result.timeouts` | số lần twin không phản ánh kịp (0) |
| `load_profile` | tải lúc đo: chỉ có luồng UDP 2 Mbps srv1 tới srv2, máy khách rảnh |

Các giá trị rải đều trong khoảng 0,2-1 s, vì độ trễ chủ yếu là thời gian chờ Sync Agent tới nhịp
đọc kế tiếp.

### `chay-lien-tuc-30-phut.json`

| Trường | Ý nghĩa |
|---|---|
| `result.samples[]` | 31 lần kiểm, mỗi phút một lần: `elapsed_s`, `rss_kib` (bộ nhớ tiến trình), `accuracy` (như phép kiểm Đúng ở trên) |
| `result.rss_start_kib`, `rss_end_kib` | 29 244 và 29 456 KiB, tức tăng 212 KiB |
| `result.all_state_accuracy_100` | `false`, vì lần kiểm đầu tiên (giây 0) chỉ khớp 7/8 |

Lần không khớp nằm ở `samples[0].accuracy.discrepancies`: twin còn ghi link h1-s1 `down` do phép
thử trước để lại, trong khi link thật đã bật. Từ lần kiểm thứ hai trở đi, mọi lần đều khớp 8/8.

## Chạy lại

| Script | Đo lại | Cần |
|---|---|---|
| `do_lai_do_tre_dong_bo_len.sh` | `do-tre-dong-bo-len.json` | testbed |
| `do_lai_doi_chieu_va_chay_30_phut.sh` | `doi-chieu-va-20-lan-tat-link.json`, `chay-lien-tuc-30-phut.json`; hơn 30 phút | testbed |

```bash
ket-qua-bao-cao/5.1-phan-chieu-trang-thai/do_lai_do_tre_dong_bo_len.sh
```

Mỗi script chạy được từ bất kỳ thư mục nào. Kết quả mới ghi vào `chay-lai/<thời điểm>/` ngay trong thư mục này, cùng tên với tệp đã lưu ở trên, nên mở hai tệp cạnh nhau là so được. Kết quả đã lưu không bị đè, kể cả khi script lỗi hay bị Ctrl-C.

Script cần testbed hỏi mật khẩu sudo một lần ở đầu, tự kiểm môi trường (`scripts/kiem_tra_moi_truong.py --testbed`) và dọn Mininet trước khi chạy. Nếu `ryu-manager` không nằm trong PATH, đặt `export DT4N_RYU=/đường/dẫn/tới/ryu-manager` trước.

Hai phép đo này chạy chung với Mục 5.2: `do_lai_do_tre_dong_bo_len.sh` đo luôn độ trễ lệnh và
phép thử HTTP 408, còn `do_lai_doi_chieu_va_chay_30_phut.sh` đo luôn thời gian từng chặng. Kết quả
của Mục 5.2 vào `chay-lai/<cùng thời điểm>/` của thư mục 5.2.

Bên trong, hai script gọi `scripts/launch_ml_preflight.py` và `scripts/run_network_suite.py`. Hai
launcher này ghi thẳng vào `results/report/`, nên đừng gọi trực tiếp trên repo có kết quả cần giữ.
Code đo: `measurements/measure_latency.py` (độ trễ), `bridge/verify.py` (đối chiếu, 20 lần tắt
link). Định nghĩa phép đo ở Mục 4.4.1 của báo cáo.
