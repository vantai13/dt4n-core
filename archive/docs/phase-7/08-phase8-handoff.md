# Hợp đồng bàn giao Phase 8

Hệ thống được phát hành theo `released = G1 ∧ G2 ∧ G3 ∧ G4 = true`
(`results/report/phase7_verdicts.json`, commit đóng băng `9917e07`).

Mỗi **điều cấm** dưới đây kèm con số đã đo làm lý do. Không có số đi kèm thì điều cấm chỉ là
một ý kiến, và ý kiến thì bị quên vào đúng lúc hệ thống đang được demo.

## R — Phase 8 ĐƯỢC ĐỌC (qua twin, `org.dt4n:detector`)

| | Trường | Ghi chú |
|---|---|---|
| **R1** | `decision.state == "act"` | Điều kiện **duy nhất** được phép hành động |
| **R2** | `evidence.affected[]` | Hành động ở đâu. **Không phải** `decision.affected` — `evidence` mô tả tick hiện tại, còn `decision` có quán tính (hysteresis) |
| **R3** | `freshness`: `(bootId, seq)` đơn điệu + TTL 3 × 1000 ms | Kiểm bằng `bridge/freshness.py::MonotonicFreshness`. Theo amendment 1: `seq` lùi, trùng, hoặc `bootId` đã retired → **bỏ cả bản tin**. Không còn là "seq + TTL" đơn thuần |
| **R4** | `provenance.releaseVersion`, `provenance.releaseSha256` | Cảnh báo này do release nào sinh ra |

## M — Phase 8 PHẢI

- **M5. Ghi `InterventionLog` TRƯỚC khi gọi `command_agent`** (write-ahead).
  *Bằng chứng 7.7:* `log_first` 0/4 vào `act`; `log_late` 4/4 có alarm lọt; `no_log` **4/4 vào
  `act`**. Ghi log sau khi hành động là tự tạo vòng phản hồi dương.
- **M6. Tôn trọng `cooldown_s = 8.0` và lease `MAX_OPEN_S = 120`**; `revert` phải được ghi log
  như `inject`. *Bằng chứng 7.6:* quên `revert` thì sau 120 s cause đổi `stale_intervention`
  (xuất hiện sau 0.29 s kể từ lúc hết hạn) và ức chế dừng.
- **M7. Có hysteresis và cooldown RIÊNG của vòng điều khiển**, độc lập với FSM của detector.
- **M8. Controller và collector cùng máy / cùng nguồn thời gian.** Ức chế so `t_start` với
  `t_source` bằng **wall clock**.
- **M9. Nếu tách controller ra tiến trình riêng:** `InterventionLog` phải đi qua IPC mà **giữ
  được write-ahead** (append xác nhận xong mới gửi lệnh). Hiện chỉ đảm bảo trong một tiến trình.

## N — Phase 8 KHÔNG ĐƯỢC

- **N10. Hành động khi `state == "suspect"`.** Precision ở mức suspect chỉ 0.90 (6R). `act`
  tồn tại chính là để tách "đáng nhìn" khỏi "đáng hành động".
- **N11. Hành động dựa trên `evidence.conservation` hoặc `evidence.actRule`.** Kênh
  conservation chậm khoảng **11 s**, vượt ngân sách 5 s (amendment 8 cấm). `actRule` không có
  quán tính: 8/28 tick `act` có `actRule = false` (7.2).
- **N12. Hành động khi `freshness` đã hết TTL.** Đó là hành động trên một trạng thái đã chết.
  *Bằng chứng:* detector chết thì twin STALE trong ≤ 3014 ms (S12, 20/20 trial).
- **N13. Tính lại state, feature hay ngưỡng.** Ba thành phần cùng tính trạng thái là ba nguồn
  sự thật, và chúng sẽ lệch nhau vào đúng lúc đang demo.
- **N14. Coi tick `suspect` chỉ-residual sau can thiệp là bug.** Đã khai trước; đo 7.7: **0**
  tick residual-only trên cả 4 lần can thiệp `admin_down`. Residual không bị ức chế bởi
  `InterventionLog` và chỉ lên tới `suspect`.
- **N15. Phản ứng với `act` có `cause == "stale_intervention"` bằng một can thiệp MỚI.**
  Đó là can thiệp **cũ của chính controller** đã hết lease 120 s (7.6). Việc đúng là **revert
  cái đang mở**. Phản ứng bằng can thiệp mới tạo vòng phản hồi dương có chu kỳ 120 giây.
- **N16. Hành động khi `cause == "out_of_operating_range"`.** Detector đang nói "tôi không có
  thẩm quyền ở tải này" (vùng hợp lệ: min txRate client ≤ 4.3126 Mbps). Im lặng ở đây là
  fail-closed có chủ đích, không phải thiếu sót.

## Giới hạn Phase 8 phải biết trước

1. **S1 = 0.30.** Envelope-only bỏ sót phần lớn sự cố mà TCP hấp thụ thành mức thông lượng
   thấp hơn. Phase 8 không được giả định "không có `act` nghĩa là mạng khỏe".
2. **Ức chế phủ 14/16 entity** trong khoảng can thiệp trên topology tam giác này. Một sự cố
   thật, độc lập, trong khoảng đó sẽ bị che.
3. **Độ đặc hiệu ở tải cao chưa được gác bởi cổng nào.** Ở 8–10 Mbps/client hàng đợi hình
   thành thường xuyên và residual có thể báo; vùng đó chỉ được S10 báo cáo, không có ngưỡng.
4. **`InterventionLog` chỉ trong một tiến trình** (xem M9).
