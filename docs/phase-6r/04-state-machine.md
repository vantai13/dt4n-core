# Phase 6R.4 — Máy trạng thái hai tầng

## 1. Đính chính kế hoạch

Envelope không dùng `d1`; `warming_up` là chính sách giao nhận, không phải
thời gian tạo feature. N đã được S4b niêm phong ở 6R.1: suspect N=1 và act
N=2, nên 6R.4 không chọn lại từ dữ liệu. Train chỉ gồm run normal và không có
revert, vì vậy không thể dùng train CV để hiệu chỉnh transient sau can thiệp.

Detector envelope trả một quyết định cho toàn mạng. Suppression cục bộ vì thế
không thể thực hiện bằng cách bỏ cột rồi tính lại excess: ngưỡng đã hiệu chỉnh
trên 71 cột và phép bỏ cột sẽ tạo training-serving skew.

## 2. Thiết kế FSM

FSM có năm trạng thái: `warming_up`, `normal`, `suspect`, `act`, `unknown`.
Các tham số đã đăng ký trước là Nₛ=1, Nₐ=2, M=3 và cooldown=8 giây.

- Một tick alarm đưa hệ vào suspect.
- Hai tick `Reading.act` liên tiếp đưa hệ vào act.
- Ba tick judgeable không alarm mới đưa suspect/act về normal.
- Đang act mà chỉ còn suspect thì vẫn giữ act.
- Unknown reset mọi bộ đếm; tick sau bắt đầu lại từ normal, không khôi phục
  bằng chứng cũ.
- Rejected không làm FSM tiến.

M=3 là số nguyên nhỏ nhất thỏa M>Nₐ, một bất biến được kiểm ngay trong
`FSMParams`. Unknown có cause thuộc enum đóng; suppression được biểu diễn là
`unknown(cause=suppressed_intervention)` để giữ hợp đồng năm trạng thái.

## 3. Suppression theo bằng chứng

Scorer trả danh sách cột vượt biên mà không thay đổi k, excess hoặc threshold.
FSM chỉ suppress khi tick đang alarm, có intervention còn hạn, tập entity của
mọi cột vi phạm có vị trí là khác rỗng và nằm hoàn toàn trong hợp blast radius.
Cột `agg.*` không có vị trí; nếu chỉ có bằng chứng aggregate thì giữ alarm.

Blast radius bậc hai được suy từ routing: lấy mọi đường host–host cắt link/flow
bị tác động rồi gom toàn bộ entity trên những đường đó. Radius được tính khi
ghi intervention và kèm SHA routing. `InterventionLog` append-only, không có
API disable/xóa, và dùng cửa sổ nửa mở `[t_start, t_start+8)`.

Chỉ sự kiện revert của harness được ghi log. Inject là sự cố, không phải hành
động khôi phục; ghi inject sẽ suppress chính tín hiệu cần phát hiện.

## 4. Công bố trước replay

Amendment 2 SHA
`31150235def13dcf4544b62b0d816885757547d1097bc3513c1b47c4306f66c4`
được push trước replay. Từ routing đã biết, radius phủ toàn bộ cột có vị trí
cho hai run flood và hai run shift. Trên topology tam giác, luật cục bộ vì thế
thoái hóa thành suppression toàn cục cho bốn run này; điều đó đã được công bố
trước khi đọc kết quả FSM.

## 5. Kết quả so với amendment 2

| Chế độ | Suspect FP events/ticks | Act FP events/ticks |
|---|---:|---:|
| Không InterventionLog | 7 / 37 | 4 / 22 |
| Có InterventionLog | 2 / 6 | 2 / 6 |

| Dự đoán | Kết quả |
|---|---|
| P1 no-log suspect events = 7 | Đạt |
| P1 no-log suspect ticks ∈ [23,44] | Đạt: 37 |
| P1 no-log act events ≤ 7 | Đạt: 4 |
| P2 full-radius runs có 0 FP | Đạt |
| P3 suspect delay khớp Phase 6 | Đạt |
| P3 act delay đã đăng ký | Đạt |
| P4 không vi phạm S7 | **Không đạt** |
| P5 normal train/control có 0 FP | Đạt |

Delay suspect trên tám run fault là `0, 0, null, 1, 0, 0, 1, 1`; delay act
là `1, 1, null, 11, 1, 2, 2, 2`. Log chỉ bắt đầu tại revert nên không làm đổi
delay trong cửa sổ sự cố.

## 6. Deviation D-6R4-1 — P4/S7 không đạt

Hai run shift không log có chuỗi sau khi bỏ unknown và gộp lặp:

```text
suspect → act → suspect → normal
```

Tick counter-reset sau revert đưa FSM vào unknown và reset bộ đếm. FP phục hồi
sau khoảng mù đưa FSM từ normal vào suspect lần nữa. Hai luật đều bảo thủ khi
xét riêng, nhưng định nghĩa S7 đã đăng ký bỏ unknown khỏi chuỗi nên tạo mẫu
`suspect→act→suspect`.

FSM không vào act lần hai, nên vòng phản hồi controller không xảy ra theo cách
đo này. Tuy nhiên P4 đã không đạt theo định nghĩa đăng ký. Không sửa định nghĩa,
không đổi unknown reset và không sửa dự đoán sau khi thấy dữ liệu. FSM chưa
được phát hành cho Phase 8 trước một amendment tiếp theo.

## 7. Finding F-6R4-1 — routing radius bỏ sót liên kết

Với log, hai run admin-down vẫn có một sự kiện FP suspect và act, kéo dài tick
41–43. Bằng chứng tại transient có cột của `link-s2-s3` nằm ngoài radius suy
từ routing của can thiệp s1-s2/s1-s3. Routing mô tả đường lưu lượng nhưng không
mô tả coupling qua kernel, CPU, veth hoặc buffer dùng chung.

Không mở rộng radius sau khi thấy kết quả. Phát hiện này quan trọng cho Phase 8:
controller có thể được phép hành động lại trên transient do chính lần phục hồi
trước tạo ra, đúng rủi ro S11.

## 8. Việc mở

Một amendment mới phải đăng ký trước cách xử lý S7: tách chuỗi tại unknown,
giữ trần trạng thái qua khoảng mù, gắn counter reset có log với intervention,
hoặc giữ nguyên và khai giới hạn. Giá trị bằng chứng phải đến từ R-O/R-C mới;
không chọn phương án bằng cách chấm lại tập test đã tiêu.

Receipt máy đọc được nằm tại `results/report/phase6r_fsm.json`.

## 9. Amendment 3 — S7 v2 suy từ mục đích

P4 của amendment 2 **giữ nguyên KHÔNG ĐẠT** và receipt cũ không được sinh lại.
S7 v1 cũng được đóng băng trong code để luôn tái tạo đúng hai vi phạm shift đã
ghi. Phân tích bảng chân lý cho thấy v1 sai theo cả hai hướng:

| Chuỗi | S7 v1 | Rủi ro cần đo |
|---|---|---|
| `act→suspect→normal→act` | Bỏ lọt | Cấp quyền act lần hai |
| `suspect→normal→act` | Bỏ lọt | Leo thang sau khi đã hạ |
| `suspect→act→suspect` | Báo vi phạm | Chỉ hạ cấp đơn điệu |

S7 v2 tách hai rủi ro:

- S7a: số lần vào act trên chuỗi thô, giữ nguyên unknown, phải ≤1.
- S7b: sau khi bỏ unknown/warmup và gộp lặp, severity
  `normal<suspect<act` phải đơn đỉnh — không tăng lại sau khi đã giảm.

Test liệt kê toàn bộ chuỗi không lặp dài 3–4 chứng minh chỗ duy nhất v2 nới
hơn v1 là hạ cấp đơn điệu có bước `act→suspect`; các thay đổi còn lại chặt hơn.
Kết quả thăm dò 16/16 trên tập test đã tiêu chỉ được công bố để minh bạch,
không phải bằng chứng. S7 v2 chỉ có hiệu lực nghiệm thu trên R-D/R-O mới.

Amendment 3 đặt bốn cổng phát hành Phase 8:

- G1: S7 v2 đạt trên mọi sự cố R-D/R-O, có và không InterventionLog.
- G2: act-level FP event bằng 0 trên R-C có InterventionLog.
- G3: S11 bằng 0 trên R-O.
- G4: S8, S9 và S12 tiếp tục đạt tiêu chí 6R.1.

Thiếu bất kỳ cổng nào thì FSM không được phát hành. Amendment cũng đóng hai
biến thể envelope V1/V2 chưa đăng ký và chỉ định nguồn chuẩn R-campaign là
`phase6r_slo.json` (27 run), với factor R-D sửa theo amendment 1.
