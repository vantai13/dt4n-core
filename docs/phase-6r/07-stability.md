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
đều đạt. S11 lần đầu **FAIL**, sau đó được chẩn đoán, đăng ký amendment 7,
sửa prospective và đo lần hai **PASS**. Cả hai receipt được giữ nguyên. Nhãn
và R-set acceptance vẫn chưa mở.

## 2. S5 — Latency

Harness đo trọn `observe() + step()` bằng `time.monotonic()`, gộp cả ba R-S.
Mỗi run bỏ 20 mẫu đầu khỏi percentile và báo cold start riêng. Không lưu hay
in latency theo tick.

| Implementation | n | p50 | p95 | p99 | max | cold max | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| OnlineScorer | 10.734 | 51,226 ms | 56,249 ms | 59,677 ms | 162,811 ms | 53,795 ms | FAIL |
| FastOnlineScorer | 10.734 | 0,771 ms | 0,943 ms | 1,291 ms | 1,676 ms | 0,996 ms | PASS |

Fast path được chọn cho Phase 7. Kết quả giải thích vì sao cần giữ hai bản:
bản pandas là tham chiếu dễ đọc nhưng vượt ngân sách 50 ms; bản NumPy đạt và
tiếp tục phải được bảo vệ bằng kiểm thử tương đương.

Receipt v1 đã gán nhầm `samples[0]` là cold start. Tick này thực chất là
`warming_up` và thoát sớm, nên các giá trị 0,622/0,658 ms không có nghĩa cold
start. `phase6r_latency_v2.json` sửa định nghĩa thành tick **scored đầu tiên**;
receipt v1 không bị ghi đè và verdict S5 không đổi. Bất đẳng thức
`max >= p99 >= p95 >= p50` được kiểm bằng code.

Đuôi bản pandas (`max/p99 ≈ 2,73`) dài hơn fast path (`≈ 1,30`), phù hợp với
chi phí cấp phát object/DataFrame và có thể có GC pause. Đây là giả thuyết cơ
chế, chưa phải phép đo GC; nếu Phase 7 xuất hiện đuôi latency, dùng
`gc.callbacks` để xác nhận.

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

Đường 30 phút tăng theo bậc: +256 KiB gần t=30 s, phẳng phần lớn thời gian,
rồi một bậc nhỏ gần cuối. Không ngoại suy tuyến tính `1,63 KiB/phút` thành mức
tăng nhiều giờ; muốn kết luận vận hành dài hạn phải soak 4–8 giờ. RSS nền là
579.456 KiB, khoảng **566 MiB**. S6 chỉ giới hạn mức tăng, còn dấu chân nền là
ràng buộc triển khai Phase 7 khi detector chạy cạnh Mininet, Ditto và dashboard.

## 4. S8/S9 — Gap và restart

Cả hai phép kiểm PASS trên tất cả checkpoint và cả ba R-S. Kết quả công khai
chỉ là AND aggregate với schema boolean cố định:

- S8/R-O2: snapshot đầu sau gap là `unknown(cause=gap)` và không có tick
  unjudgeable nào thành `normal`.
- S9/R-O1: snapshot đầu sau restart là `warming_up`, không vào `act` trước
  `n_act`, và không thành `normal` trước một kết quả scored.

Không có chuỗi state, số alarm, tick, timestamp, entity hay score được lưu.
Firewall bị khóa bằng `ml/replay_guard.py` và mutation test tổng hợp.

## 5. S11 — FAIL, chẩn đoán, sửa và đo lần hai

Receipt v1 **FAIL** trên cả hai run: mỗi run có 1 lần vào `act` và 0 tick
`suppressed_intervention`. Chẩn đoán chi tiết chỉ chạy trên RO-ctl, không chạy
trên R-S, đã bác bỏ H1 và xác nhận H2:

- tick 21–28 đều `scored` và alarming, không phải `unknown`;
- `link-s2-s3` nằm ngoài radius ở tick 21;
- từ tick 22, cả `link-s1-s3` và `link-s2-s3` nằm ngoài radius;
- điều kiện an toàn `local ⊆ zone` vì vậy từ chối suppression.

`radius()` không có bug: nó trả lời đúng câu hỏi nó được viết cho, *"luồng nào
đang đi qua link này?"*, bằng cách tra bảng định tuyến đã đóng băng. Nhưng bán
kính ảnh hưởng là một đại lượng **phản thực**, và câu hỏi cần trả lời là *"khi
tôi tắt link này thì chỗ nào sẽ thay đổi?"*. Khoảng cách giữa hai câu hỏi đó
chính là lỗ hổng: các tuyến trước hành động đi qua `s1-s2`, nên hành lang
detour vật lý `s1-s3-s2` không có trong radius, dù chính nó nhận lưu lượng sau
khi link bị tắt.

Độ lệch một tick giữa hai link là **bằng chứng cơ chế**, không phải nhiễu:

| Tick | Sự kiện | Khoảng cách topology |
|---|---|---|
| 20 | `admin_down` được áp (apply 6,9 ms) | — |
| 21 | `link-s2-s3` lệch trước | hiệu ứng gần: TCP trên `s1-s2` dừng đột ngột, tranh chấp hàng đợi tại `s2` đổi ngay, luồng qua `s2-s3` đổi rate |
| 22 | `link-s1-s3` cũng lệch | hiệu ứng xa hơn một chặng: ARP/TCP retransmit và tái phân bố cần thêm một chu kỳ mới hiện ra |

`s2` là switch trực tiếp chịu tác động; `s1-s3` xa hơn một chặng. Thứ tự này
giống nhau ở cả hai seed 4301 và 4302, nên đây là sóng lan theo topology, không
phải trùng hợp: nếu hai link lệch cùng lúc, hoặc lệch ở tick khác nhau giữa hai
seed, lý giải cơ chế sẽ yếu đi nhiều.

Amendment 7 (`f80b5cfd…`) được commit trước code và công khai đây là sửa sau
khi biết FAIL. Bản sửa gồm:

1. `inject` mở một khoảng, `revert` đóng khoảng; cooldown 8 s chỉ áp dụng sau
   khi đóng. Inject không được đóng là lease tối đa 120 s, sau đó detector
   ngừng suppression và phát `stale_intervention`.
2. `admin_down` bổ sung đúng hành lang detour ngắn nhất khi bỏ link mục tiêu.
   Với `s1-s2`, radius thêm `switch-s3`, `link-s1-s3`, `link-s2-s3`. Không
   chuyển subset thành intersection và không mở rộng mù toàn mạng.

Ba lựa chọn khác đều tệ hơn và đã bị loại:

| Lựa chọn | Vì sao sai |
|---|---|
| `local ∩ zone ≠ ∅` | Một sự cố thật ngoài vùng, xảy ra cùng lúc, bị che chỉ vì trùng một entity: đổi lỗi bỏ sót cục bộ thành bỏ sót toàn cục |
| Ức chế toàn mạng | Detector mù hoàn toàn trong mỗi lần controller hành động; phá S1 và S4 |
| Nâng `cooldown_s` lên 30 | Sai công cụ: cooldown dành cho transient *sau* can thiệp, không phải thời lượng *của* can thiệp; và vẫn không sửa H2 |

Điểm mấu chốt: luật tập con **không bị nới**; `zone` được làm cho **đúng** hơn.

Sửa được thực hiện theo nguyên tắc **cộng thêm, không đột biến**: `radius()`
giữ nguyên byte-for-byte và `radius_with_detour()` là hàm mới, nên bằng chứng
`phase6r_fsm.json` của 6R.4 — vốn ghim SHA của `radius()` qua amendment 2 — vẫn
tái lập được và không phải chạy lại. Cùng khuôn này áp cho cả ba receipt v2
(`replay_o3`, `latency`, `stability`): bản cũ không bị ghi đè.

Tính tất định của hành lang detour được khóa bằng
`test/test_blast_radius_detour_reproducible.py`: BFS duyệt láng giềng qua
`sorted()`, nên khi Phase 7 mở rộng topology và có nhiều đường ngắn nhất bằng
nhau, radius vẫn không phụ thuộc `PYTHONHASHSEED`. Một receipt không tái lập
được thì không phải bằng chứng.

Receipt v2 dùng đúng hai run cũ, không thu thêm dữ liệu và không đổi ngưỡng:

| Run | act entry | suppressed tick | Kết quả |
|---|---:|---:|---|
| seed 4301 | 0 | 21 | PASS |
| seed 4302 | 0 | 21 | PASS |

S11 offline hiện PASS theo cả hai điều kiện; receipt FAIL v1 vẫn được ghim.
G3 chỉ đạt ở harness offline. Phase 8 vẫn bị khóa cho tới khi Phase 7 đạt S11
live và S12.

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
- S11 đã sửa và PASS offline, nhưng controller Phase 7 live chưa được kiểm.
- Latency đo detector riêng trên Python 3.13.13, Linux 6.8.0-1066-gcp,
  Intel Xeon 2,80 GHz/8 logical CPU. Chưa đo tranh chấp CPU khi Mininet,
  Ditto và dashboard cùng chạy.

Receipt v1 là `results/report/phase6r_stability.json`. Receipt ra quyết định mới
là `results/report/phase6r_stability_v2.json`; nó ghim nguyên v1, amendment 7,
hai receipt S11, hai receipt latency và code sửa. Không file lịch sử nào bị
ghi đè.
