# Lesson 6R.5B — Thu R-campaign (25 run, outcome-blind)

## Giao thức metrology đăng ký trước khi đo

Phép đo jitter trên raw R-S chỉ đọc trường `t_rel`. Nó không đọc nhãn, không
import scorer/model, không sinh alarm và không trả về trạng thái FSM. Đây là
phép đo metrology hợp lệ theo ngân sách dữ liệu §6, dùng để định lượng độ phủ
mất bởi quyết định đã khóa ở 6R.3: `delta-t > 1.5 s` thì `d1 = unknown`.

Giao thức cố định trong `scripts/measure_tick_jitter.py`: ba run R-S đã đăng
ký, ngưỡng 1,5 giây, các percentile p50/p95/p99, maximum, số khoảng vượt ngưỡng
và vị trí tối đa 20 khoảng đầu để truy nguyên. Script ghi receipt có SHA-256 và
từ chối ghi đè. Phần kết quả của tài liệu này chỉ được điền sau khi giao thức
và test phạm vi đã commit.

## Trạng thái trước phép đo

- R-campaign: 25/25 run đạt, receipt đã được Amendment 6 ghim SHA.
- R-set: chưa mở, `labels_opened = false`.
- R-O replay: chưa chạy; tường lửa boolean-only đã đăng ký trong Amendment 6.

## Điều kiện và kết quả thu

- Hợp đồng khóa lúc `2026-09-17T10:57:16Z`; run đạt đầu tiên bắt đầu lúc
  `11:32:10Z`.
- Amendment 5 ghi lúc `11:27:05Z`, ghim SHA năm file runtime trước khi thu.
- 25 run đạt kéo dài tới `16:21:45Z`, khoảng 4 giờ 50 phút gồm một lần chạy
  lại soak và một lần dừng vì health gate Ditto.
- Contract integrity: stored và recomputed cùng bằng
  `3ea21c675a716723ae0289ad10490483ceb8c31e976443f3fcc791bb1514f04f`.
- Chuỗi SHA manifest ↔ sidecar ↔ raw/LFS khớp 25/25; thứ tự thời gian khớp
  `exec_index` ngẫu nhiên đã khóa 25/25.

| Nhóm | Kỳ vọng | Đạt | Ghi chú |
|---|---:|---:|---|
| R-S | 3 | 3 | 3598/3600 snapshot mỗi run, trong tolerance |
| R-N | 6 | 6 | 6/8/10 Mbps/client × 2 seed |
| R-D | 10 | 10 | 5 bậc rho × 2 link |
| R-C | 4 | 4 | flood ×2, shift ×2; tập hiệu chỉnh |
| R-O3 | 2 | 2 | controller `admin_down` |

Receipt cuối ghi `complete=true`, `n_runs_failed=0`, `runs_not_attempted=[]`
và `labels_opened=false`. Test `test_rcampaign_manifest.py` ghim receipt bằng
SHA đã đăng ký trong Amendment 6.

## Lần chạy lại và lỗi môi trường

Lần thử đầu của `RS-soak2M-s4003-r3` bị cách ly chỉ vì
`runtime_log_ok=false` (`runtime_error_count=1`). Dòng lỗi nguyên văn:

```text
2026-09-17 14:57:52,075 [ERROR] pusher: PATCH org.dt4n.ml:host-h2 bỏ cuộc sau 4 lần: HTTPConnectionPool(host='localhost', port=8080): Read timed out. (read timeout=5)
```

Mọi gate dữ liệu của lần thử đó đều đạt: 3598/3600 snapshot nằm trong dung sai,
qdisc/rate invalid bằng 0 và không có link down ngoài dự kiến. `runtime_log_ok`
thuộc `INSTRUMENT_GATES` trong code có SHA
`1531f791a1b76b81a432ccdf286725f17acf4316e20d2b59f8c19f713e76c835`,
được Amendment 5 ghim trước run đầu. Lỗi là timeout hạ tầng Ditto, không phụ
thuộc kết cục detector. Lần thử hỏng được giữ trong quarantine với raw SHA
`896c1b61346fdc45fddc904a49d75e5b4831707a643b26c2ac3be87637a146bc`.

Trước run R-O3 còn có một lần health gate dừng vì Ditto thiếu throughput
`srv1/srv2`; lỗi xảy ra trước khi có raw run, sau đó launcher resume đúng hợp
đồng. Sự kiện này không được tính là một accepted/quarantined run attempt.

## Kết quả metrology delta-t

Giao thức ở đầu tài liệu được commit trước phép đo. Receipt
`phase6r_tick_jitter.json` có SHA nội dung
`bf14728178905c8eaada611f24bfef1b9ed0e261cd2ec5eee2b61f454bd1fdec`.

| Run | Khoảng | p50 | p95 | p99 | Max | >1,5 s |
|---|---:|---:|---:|---:|---:|---:|
| RS-s4001 | 3597 | 1,0007 s | 1,0051 s | 1,0091 s | 1,0892 s | 0 |
| RS-s4002 | 3597 | 1,0006 s | 1,0051 s | 1,0091 s | 1,0912 s | 0 |
| RS-s4003 | 3597 | 1,0006 s | 1,0054 s | 1,0091 s | 1,0858 s | 0 |

Gộp ba run: 0/10.791 khoảng vượt 1,5 giây; độ phủ mất đo được bởi chính sách
delta-t là 0%. Mỗi run có 3598 snapshot nhưng `t_rel_last≈3599,35 s`, không có
khoảng trống giữa run. Nguyên nhân là mỗi chu kỳ dài hơn 1 giây khoảng 0,6 ms;
drift tích lũy khoảng 2,3 giây làm deadline 3600 giây chứa ít hơn hai lần ghi.
Đây là hiệu ứng biên thời gian, không phải gap S8.

## Provenance và giới hạn đã biết

- 20/25 sidecar ghi `source_dirty=true` với `source_dirty_files` chỉ gồm
  `data/phase6r/`. Đây là lỗi phân loại của `collection_provenance`, vốn chỉ
  loại `data/phase5/`; không có file source code nào bẩn. Không sửa receipt đã
  niêm phong. Test manifest khóa rằng tập bị gắn cờ không vượt quá đúng thư mục
  runtime này và mọi run dùng cùng commit `ba490d2`.
- R-N bắt đầu ở 60% dung lượng s1-s2; dải 40–60% chưa được lấy mẫu. Nếu có báo
  động ở 60%, dữ liệu hiện tại không định vị được ngưỡng bên trong khoảng đó.
- 10 Mbps/client đưa s1-s2 tới 100% dung lượng; báo động tại đó phải được phân
  loại theo luật căn cứ vật lý của Amendment 4, không mặc định là false positive.
- Raw khoảng 130 MB dùng Git LFS; README ghi cách tải và kiểm pointer.
- R-O1/R-O2 chưa replay. Amendment 6 khóa API boolean-only trước khi harness
  được viết, ngăn việc nhìn chuỗi trạng thái/alarm của R-S.

## Điều chưa được chứng minh

Chưa chấm một tick R-set nào và chưa chạy scorer/FSM trên raw R-campaign.
S1–S13, ED50, recall, FPR và các release gate chưa có kết quả nghiệm thu;
chúng chỉ được mở theo giao thức Lesson 6R.7.
