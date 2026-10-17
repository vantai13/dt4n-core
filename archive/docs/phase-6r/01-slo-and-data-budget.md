# Lesson 6R.1 — SLO vận hành, ngân sách dữ liệu, thiết kế R-campaign

Artifact: `results/report/phase6r_slo.json`  
`content_sha256`: `a80fd5fb0325dac2e54c4aaf89c7610fec4de7aa082d3bfdaa1aaf56a4147ee3`  
Commit niêm phong: `12119dd962113a1fa94b6ad3be342a31ebe18f78` — đứng trước mọi code 6R.

## 1. Vấn đề

Nếu mục tiêu “ổn định” chỉ được đặt sau khi xem kết quả thì mọi lần chỉnh tham số
đều có thể được hợp thức hóa. Lesson này đăng ký trước định nghĩa thành công, nguồn
dữ liệu được phép dùng và campaign nghiệm thu. JSON là hợp đồng cho máy; tài liệu
này giải thích cơ sở của hợp đồng cho người đọc.

Chúng tôi chọn trước `SOAK_MINUTES=60` và chọn làm nhóm hiệu chỉnh độc lập `R-C`
gồm bốn run. Các lựa chọn này được chốt trước khi viết code detector Phase 6R.

## 2. Chỉ số offline không phải SLO vận hành

### 2.1 Vì sao `FPR × 3600` sai trong hệ này

| Cửa sổ | Tick âm | FP excess | FP dual | Unknown |
|---|---:|---:|---:|---:|
| Control, toàn run | 118 | 0 | 0 | 0 |
| Fault run, trước inject | 160 | 0 | 0 | 0 |
| Fault run, sau revert | 152 | 23 | 2 | 4 |
| Tổng | 430 | 23 | 2 | 4 |

Có 0 FP trên 278 tick nền tĩnh và có 7 chùm FP excess, tất cả sau thay đổi cấu
hình. Vì vậy FP không được mô hình như quá trình đều theo thời gian. Mô hình vận
hành là:

`lambda_false = f_change × P(cluster | change) + p_steady × 3600`

Thành phần đầu đã quan sát được 7/8 sự kiện sau thay đổi; thành phần nền mới chỉ
có quan sát 0/278 và chưa đủ dữ liệu. Cơ chế trực tiếp xử lý nguyên nhân đã đo là
change-aware cooldown; debounce không loại được chùm hậu-revert và làm tăng trễ.

### 2.2 Mask làm cơ sở

| Mask | Recall excess | FPR excess | Recall dual | FPR dual |
|---|---:|---:|---:|---:|
| `eval_primary` | 85.625% | 5.349% | 79.375% | 0.465% |
| `eval_sensitivity` | 87.500% | 3.382% | 81.944% | 0% |

Mọi SLO được neo vào `eval_primary`, mask đã đăng ký và bất lợi hơn.
`eval_sensitivity` loại đúng các tick onset/recovery nơi FP tập trung nên chỉ được
dùng để mô tả bản chất FP, không làm mẫu số SLO.

### 2.3 Rule of three và giới hạn dữ liệu

Khi quan sát 0 sự kiện trên `n` tick, giới hạn trên một phía 95% xấp xỉ `3/n`.

| Ngân sách | Tick | Giới hạn trên alarms/hour nếu 0 FP |
|---|---:|---:|
| Control test | 118 | 91.5 |
| Control + pre-inject | 278 | 38.8 |
| Train held-out CV | 472 | 22.9 |
| 15 run × 59 tick | 885 | 12.2 |
| Soak 60 phút | 3,600 | 3.0 |
| Soak 180 phút | 10,800 | 1.0 |

Do đó S2 `≤3 alarms/hour` và S3 `MTBFA ≥20 phút` cần soak 60 phút. S2 và
S3 là hai cách biểu diễn cùng một phép đo, không phải hai chứng cứ độc lập.

## 3. Bảng SLO đã niêm phong

| ID | SLI | Mục tiêu | Nguồn | Campaign |
|---|---|---|---|---|
| S1 | Detection theo incident, suspect | ≥7/8 | Phase 6 delay | R-D |
| S2 | Alarm sai/giờ, nền tĩnh | ≤3/h, upper 95% | rule of three, soak 60 phút | R-S |
| S3 | MTBFA nền tĩnh | ≥20 phút, lower 95% | cùng phép đo S2 | R-S |
| S4 | TTD p95 | ≤3,000 ms | ngân sách end-to-end 5 s | R-D, R-O |
| S4b | Debounce ceiling | `N≤2` | suy từ S4 | suy diễn |
| S5 | p95 `observe()+step()` | ≤50 ms | ≤5% chu kỳ tick | R-S |
| S6 | RSS tăng sau 30 phút | ≤1 MiB | soak Phase 2: +212 KiB | R-S |
| S7 | Dao động | 0 mẫu `X→Y→X` | chống feedback | R-D, R-O |
| S8 | Dữ liệu thiếu | 100% → unknown; 0% → normal | DT4N-M1 | R-O |
| S9 | Tick đầu sau restart | 100% đúng policy | gate Phase 7 | R-O |
| S10 | Tải ngoài calibration | báo cáo, không đặt target | chưa từng đo | R-N |
| S11 | Tự kích hoạt | 0 lần vào act do controller | chống feedback | R-O |
| S12 | Detector chết | twin stale trong ≤5 s, TTL 3 tick | gate Phase 7 | R-O |
| S13 | Truy vết model | 100% payload có version + artifact SHA | điều tra Phase 8 | unit test |

### 3.1 Ràng buộc debounce suy trước dữ liệu

`t_detect = (onset + N - 1) × 1000 + compute`, với onset p95 1 tick và
compute budget 50 ms. N=1 cho 1,050 ms; N=2 cho 2,050 ms; N=3 cho 3,050 ms
và vi phạm S4. Đăng ký trước: suspect dùng N=1, act dùng N=2. Giá trị cuối vẫn
phải được xác nhận bằng train CV theo ngân sách dữ liệu.

### 3.2 S12 và S13

S9 chỉ phủ restart tạm thời. S12 phủ detector chết vĩnh viễn để dashboard không
giữ màu xanh giả khi dữ liệu đã cũ. S13 yêu cầu mọi state có `modelVersion` và
`artifact_sha256`, cho phép truy nguyên model khi controller đã hành động.

## 4. Ngân sách dữ liệu

| Quyết định | Được phép | Cấm |
|---|---|---|
| E, K | artifact Phase 6 đã đóng băng | refit |
| `link_stats` | manifest đã đóng băng | tính lại từ serving data |
| Bounds 71 cột | manifest envelope | refit |
| Trần N | ngân sách S4 | dùng nhãn |
| N cuối | train CV; replay test chỉ đếm chùm không nhận `y` | nhãn test |
| Cooldown | prior 8; giá trị cuối từ R-C | R-O và test Phase 6 |
| TTL | quyết định thiết kế 3 tick | — |
| Threshold biến thể | train CV | test, R-set |
| Chọn biến thể | đăng ký trước; nghiệm thu R-set một lần | thử lần hai |

Envelope có 71 feature nhưng 0 feature `d1`; scorer stateless theo feature. Nguồn
training-serving skew còn lại là `link_stats`, phải nạp từ manifest đóng băng.

### 4.1 Replay test không tiêu test

Kiểm tra tương đương chỉ nhận `(run_id, tick, alarm)` và không nhận nhãn `y`.
Nó có thể tìm khác biệt giữa batch và online nhưng không thể chỉ ra threshold nào
cho kết quả đẹp hơn. Chữ ký hàm là hàng rào thi hành quy tắc này.

### 4.2 Cooldown: prior 8 đến R-C

Giá trị 8 đến từ diagnostic hậu-freeze trên run test nên chỉ là prior có khai báo.
R-C gồm flood ×2 và shift ×2; cooldown cuối bằng span hậu-revert lớn nhất trên
R-C cộng một tick.

## 5. Ma trận R-campaign

| Nhóm | Runs | Núm xoay | Vai trò | Lặp? |
|---|---:|---|---|:---:|
| R-S | 3 | load 2M, không fault, 60 phút/run | nghiệm thu S2/3/5/6 | Không |
| R-N | 6 | 6/8/10 Mbps × 2 seed | nghiệm thu S10 | Không |
| R-D | 10 | 5 factor × 2 link, degrade | dose-response, ED50 | Không |
| R-C | 4 | flood ×2, shift ×2 | hiệu chỉnh cooldown | Không |
| R-O | 4 | restart/drop/kill/controller action | nghiệm thu logic | Có |

Mỗi run phải được khai trước với `run_id`, seed, git hash, fault parameters, load,
duration và vai trò hiệu chỉnh/nghiệm thu.

### 5.1 R-S

885 tick chỉ hỗ trợ giới hạn 12.2 alarm/h. R-S là điều kiện bắt buộc để phát biểu
S2/S3 ở mức đã đăng ký, đồng thời đo đầy đủ latency và RSS.

### 5.2 R-N

Ở 8–10 Mbps, alarm có thể là phát hiện nghẽn đúng. Báo cáo tách hai cột: FP thật
không kèm bằng chứng vật lý, và phát hiện nghẽn có `lossPct>0`,
`qdiscDropDelta>0` hoặc `state_up==0`.

### 5.3 R-D

Factor chỉ là núm xoay. Hai factor 0.8275 và 0.8203 gần nhau nhưng separation lần
lượt 11.486 và 288.827 vì routing và headroom khác nhau. Liều là
`max_separation` đo sau bằng `ml.campaign.signal_check`. Hồi quy đăng ký trước là
`detected ~ log10(separation)`, báo ED50 và cluster-bootstrap CI theo run, chỉ
trong họ degrade. `admin_down=100` là hằng số cấu trúc từ floor 0.01 nên không
được trộn vào đường này. Khoảng chưa biết là `(11.486, 100.0)`.

### 5.4 R-C

R-C tách hiệu chỉnh cooldown khỏi test Phase 6 và khỏi các run nghiệm thu.

### 5.5 R-O

R-O kiểm mệnh đề logic tất định nên có thể lặp sau khi sửa bug. Nếu kết quả R-O
khiến ta muốn đổi threshold thì phải dừng: đó là hiệu chỉnh, không còn là kiểm
tra logic.

## 6. Sai lệch so với PHASE_6R.md

| Plan cũ | Sửa | Bằng chứng |
|---|---|---|
| Neo 87.5%/3.38% | Neo 85.625%/5.35% | `eval_primary` prereg |
| `FPR×3600` | Mô hình hai thành phần | 0/278 nền, 7 cluster hậu-revert |
| S2 ≤1/h với 885 tick | S2 ≤3/h, soak 60 phút | rule of three |
| Envelope stateful vì d1 | Feature stateless | 0/71 cột d1 |
| Factor là dose | Separation là dose đo sau | 11.486 vs 288.827 |
| Gộp các họ fault | Chỉ fit trong degrade | admin_down bị ghim 100 |
| Cooldown 8 đã đóng băng | 8 là prior, R-C hiệu chỉnh | nguồn là test diagnostic |
| S7 ≤2 transition | S7 = 0 mẫu X→Y→X | escalation hợp lệ có 3 transition |
| 11 SLO | Thêm S12, S13 | staleness và provenance |

## 7. Điều lesson này không quyết định

- Giá trị N cuối; việc đó dùng train CV ở 6R.4.
- Giá trị cooldown cuối; việc đó dùng nhóm hiệu chỉnh R-C.
- Target cho S10; hiện chỉ đăng ký cách báo cáo hai cột.
- Kết quả nghiệm thu R-S/R-N/R-D/R-O; campaign chưa được chạy trong lesson này.
