# Lesson 6R.7 — Nghiệm thu một lần trên R-set

Receipt: `results/report/phase6r_acceptance.json` (content SHA
`f551f950b744775c484fab6a050b52be702c935119916f22d857cd2441ced0d7`).
Phán quyết nằm ở `phase6r_verdicts.json`, được code tính từ receipt và SLO;
không phán quyết PASS/FAIL nào được gõ tay.

## 1. Quy trình

- Prereg được đóng trước tag `phase-6r-opened`.
- Có 5 rehearsal trên Phase 5/6 và đúng 1 invocation `mode=acceptance`, tại
  HEAD `e6bdb9e`.
- Skeleton 539 key-path, toàn bộ lá null, đã commit tại `0c31d49`.
- Sau khi mở không đổi tham số và không chấm lại. Amendment 8 công khai được
  viết sau khi mở và chỉ quyết định triển khai.

## 2. Bảng SLO

| SLO | Mục tiêu | Kết quả kênh đăng ký | Phán quyết | Ghi chú |
|---|---|---|---|---|
| S1 | ≥ 0.875 | 0.30 (3/10, envelope) | **FAIL** | combined 0.60, chỉ mô tả |
| S2 | ≤ 3.0/h, cận trên 95% | 0 sự kiện/2.9975 h; ≤ 0.9994/h | PASS | |
| S3 | ≥ 20 phút, cận dưới 95% | ≥ 60.04 phút | PASS | cùng phép đo với S2 |
| S4 | ≤ 3000 ms | 2007 ms, envelope | PASS | combined 11001 ms: không đạt |
| S4b | N ≤ 2 | 2 | PASS | 6R.6 |
| S5 | ≤ 50 ms | p95 0.943 ms | PASS | detector-only |
| S6 | ≤ 1 MiB | +0.285 MiB | PASS | 6R.6 |
| S7 | 0 mẫu dao động | 0 (G1) | PASS | |
| S8, S9 | 100% | 100% | PASS | replay boolean-only |
| S10 | báo cáo | xem §5 | REPORT_ONLY | không có ngưỡng pass/fail |
| S11 | 0 act do controller | 0, offline sau A7 | PASS | chưa thay S11 live |
| S12 | stale ≤ 5 s | — | DEFERRED | Phase 7 |
| S13 | 100% truy vết | 100% | PASS | release mở rộng cho residual |

Gates: G1, G2, G3 PASS; G4 false và `released=false`. G4 là kết luận định
trước vì S12 thuộc Phase 7, không mang thông tin về R-set.

## 3. S1 FAIL và phân tầng POST-HOC

Phán quyết đăng ký là FAIL. Phân tầng sau chỉ mô tả, không thay phán quyết:

| Nhóm | envelope | combined |
|---|---:|---:|
| ρ ≥ 1.10 (6 run) | 3/6 | 6/6 |
| ρ ≤ 0.90 (4 run) | 0/4 | 0/4 |

R-D cố ý có bốn run ρ ≤ 0.8 không tạo tác động đủ để hai kênh phát hiện. SLO
tương lai nên đăng ký trước mẫu số “sự cố có tác động quan sát được”.

## 4. Hai kênh bù nhau

| Link | ρ | envelope | residual |
|---|---|---|---|
| s1-s2 | 2.0 / 1.5 / 1.25 | ✗ ✗ ✗ | ✓ ✓ ✓ |
| s2-s3 | 2.0 / 1.5 / 1.25 | ✓ ✓ ✓ | ✓ ✓ ✗ |

Degrade s1-s2 tạo hàng đợi không mất gói và không cột envelope nào vượt biên,
nhưng switch s1 có vào lớn hơn ra. Trên s2-s3, envelope thấy 3–8 cột vượt
biên; residual bị pha loãng và không phát hiện run ρ=1.25.

## 5. S10 và vùng vận hành

Ở 6 Mbps/client, cả hai run có 0/59 alarm tick. Ở 8 Mbps, cả hai run có 59/59
alarm tick và 59 strict-FP tick. Ở 10 Mbps, mỗi run có 59/59 alarm tick nhưng
50 strict/sensitive-FP và 46 residual-FP tick. Vùng nghiệm thu là 2
Mbps/client; guard vùng vận hành được chuyển sang Phase 7 theo amendment 8.

## 6. Dự đoán đã đăng ký

| Dự đoán | Kết quả |
|---|---|
| P_S2: 0 sự kiện → cận trên khoảng 1.0/h | Đúng |
| P_S4 envelope ≤ 3000 ms | Đúng, 2007 ms |
| P_S4 combined có phát hiện muộn > 3000 ms | Đúng, 10–11 s |
| P_F2: ρ=0.5/0.8 không bị phát hiện | Đúng, 0/4 |
| P_F3: nền residual ≤ 2% | Đúng |
| P_ED50: CI rộng/có thể không hội tụ | Đúng |
| P_S10: ở 10 Mbps col_b < col_a rõ rệt | **Sai**, 50=50 |
| P_G4 không đóng được trong 6R | Đúng |

## 7. Liều–đáp ứng

Fit đăng ký cho envelope: ED50 27.999, CI95 [2.657, 141.408], 1125/2000
bootstrap hội tụ. Fallback đã đăng ký cho thấy toàn bộ envelope không đơn điệu:
overlap [5.433, 27.482], 3 inversion. Riêng s1-s2 là `censored_all_miss`
(0/5); s2-s3 có bracket [0.068, 5.433]. Combined có bracket [0.174, 5.433]
và ED50 fallback 0.972. Vì vậy link lỗi quan trọng hơn một trục separation
duy nhất.

## 8. D-6R7-1 — POST-HOC mô tả

Chẩn đoán được đăng ký trong amendment 8 trước khi chạy. First residual alarm
ở tick 30, 30, 31 cho ρ lần lượt 2.0, 1.5, 1.25. Sau tick unknown 21,
`r_max` có transient giảm rồi mới ramp qua R; nó không tăng đơn điệu ngay từ
tick 22. Kết quả phù hợp một phần với tích lũy có transient và chỉ cho thấy ảnh
hưởng ρ yếu (một tick), không chứng minh mô hình tích lũy đơn thuần. Không số
nào từ chẩn đoán được dùng để đổi R, verdict hoặc release.

## 9. Điều chưa chứng minh

S12 và S11 live; hành vi 3–6 Mbps; cơ chế cửa sổ sau revert của F-6R4-1;
guard vùng vận hành; và tranh chấp CPU end-to-end vẫn chuyển sang Phase 7.
