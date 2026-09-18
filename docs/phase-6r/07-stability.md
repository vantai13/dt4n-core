# Lesson 6R.6 — Hồ sơ ổn định

## 1. Phạm vi đã hiệu chỉnh

Phạm vi được khóa trước phép đo trong
`results/report/phase6r_stability_prereg.json`. Nguồn thẩm quyền là bảng SLO
đã niêm phong, amendment 4 và amendment 6; checklist cũ trong `PHASE_6R.md`
không được dùng để mở sớm protected estimand.

| Nhóm | Kết quả |
|---|---|
| Đo/kiểm tại 6R.6 | S4b, S5, S6, S8, S9, S11, S13 |
| Hoãn đúng kế hoạch sang 6R.7 | S1, S2, S3, S4, S7, S10 |
| Hoãn sang Phase 7 | S12 |

Việc “đóng tại 6R.6” nghĩa là phép kiểm đã hoàn thành, không có nghĩa mọi SLO
đều đạt. S11 đã được đo và **FAIL**. Nhãn và R-set acceptance vẫn chưa mở.

## 2. S5 — Latency

Harness đo trọn `observe() + step()` bằng `time.monotonic()`, gộp cả ba R-S.
Mỗi run bỏ 20 mẫu đầu khỏi percentile và báo cold start riêng. Không lưu hay
in latency theo tick.

| Implementation | n | p50 | p95 | p99 | max | cold max | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| OnlineScorer | 10.734 | 51,953 ms | 58,029 ms | 61,454 ms | 190,365 ms | 0,622 ms | FAIL |
| FastOnlineScorer | 10.734 | 0,775 ms | 0,927 ms | 1,164 ms | 1,733 ms | 0,658 ms | PASS |

Fast path được chọn cho Phase 7. Kết quả giải thích vì sao cần giữ hai bản:
bản pandas là tham chiếu dễ đọc nhưng vượt ngân sách 50 ms; bản NumPy đạt và
tiếp tục phải được bảo vệ bằng kiểm thử tương đương.

## 3. S6 — Bộ nhớ

Measurement of record chạy 1.800 tick ở 1 Hz trong 1.800,2 giây. RSS lấy từ
`/proc/self/statm`, không dùng high-water mark `ru_maxrss`.

| Thang đo | Tick | Thời gian | RSS đầu → cuối | Delta | Lỗi | Nhận xét |
|---|---:|---:|---:|---:|---:|---|
| Real-time | 1.800 | 1.800,2 s | 579.456 → 579.748 KiB | 292 KiB / 0,2852 MiB | 0 | PASS, nửa sau 1,63 KiB/phút, flat |
| Accelerated | 10.794 | 8,8 s | 579.748 → 579.752 KiB | 4 KiB / 0,0039 MiB | 0 | bằng chứng bổ sung theo tick |

Nhãn cơ học `still_growing` của accelerated không phải bằng chứng rò: chuỗi
chỉ có ba mẫu trong 8,8 giây và thay đổi đúng một page 4 KiB, khiến phép ngoại
suy slope ngắn hạn thành 63,16 KiB/phút. Verdict S6 chỉ dùng đường real-time
đã đăng ký trước. Đồ thị: `results/report/phase6r_soak_rss.png`.

## 4. S8/S9 — Gap và restart

Cả hai phép kiểm PASS trên tất cả checkpoint và cả ba R-S. Kết quả công khai
chỉ là AND aggregate với schema boolean cố định:

- S8/R-O2: snapshot đầu sau gap là `unknown(cause=gap)` và không có tick
  unjudgeable nào thành `normal`.
- S9/R-O1: snapshot đầu sau restart là `warming_up`, không vào `act` trước
  `n_act`, và không thành `normal` trước một kết quả scored.

Không có chuỗi state, số alarm, tick, timestamp, entity hay score được lưu.
Firewall bị khóa bằng `ml/replay_guard.py` và mutation test tổng hợp.

## 5. S11 — Chống tự-kích-hoạt

S11 **FAIL**, trái dự đoán prereg. Cả hai run RO-ctl đều có:

- 1 lần vào `act` trong `[inject, revert + cooldown]`;
- 0 tick mang `cause=suppressed_intervention`;
- blast radius đã có trong `sidecar.interventions`, nhưng không có bằng chứng
  rằng điều kiện suppression hiện tại đã kích hoạt.

Kết quả dùng `sidecar.interventions` ghi trước lúc apply theo amendment 5,
không dùng `events`. Không đổi cooldown, radius, ngưỡng hoặc cách đếm sau khi
thấy FAIL. Vấn đề phải được xử lý bằng một thay đổi prospective và dữ liệu mới;
hai run đã đo không được diễn giải lại. Vì controller ở đây vẫn là harness,
đây cũng chưa phải kiểm chứng controller Phase 8 thật.

## 6. S13 và S4b

S13 PASS: `ml/payload.py` sao chép quyết định FSM và bắt buộc payload có
`modelVersion` cùng `artifactSha256`; payload không tính lại trạng thái.

S4b PASS bằng suy diễn đã được biến thành test:

```text
t_detect(N) = (1 + N - 1) × 1000 ms + 50 ms
N=2: 2050 ms <= 3000 ms
N=3: 3050 ms > 3000 ms
=> trần debounce N <= 2
```

Tham số đã khóa là `n_suspect=1`, `n_act=2`.

## 7. Chưa chứng minh được

- S1/S2/S3/S4/S7/S10 chưa được nghiệm thu; `labels_opened=false` và
  `r_set_acceptance_opened=false`.
- S12 thuộc Phase 7 theo amendment 4.
- S11 hiện thất bại và mới chạy với controller harness.
- Latency đo detector riêng trên Python 3.13.13, Linux 6.8.0-1066-gcp,
  Intel Xeon 2,80 GHz/8 logical CPU. Chưa đo tranh chấp CPU khi Mininet,
  Ditto và dashboard cùng chạy.

Receipt tổng là `results/report/phase6r_stability.json`; receipt pin prereg,
code triển khai, năm evidence JSON và SHA-256 của đồ thị.
