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
