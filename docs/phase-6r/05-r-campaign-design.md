# Lesson 6R.5A — Thiết kế và khóa hợp đồng R-campaign

## Mục tiêu của từng nhóm

| Nhóm | Số run thu | Câu hỏi | Quyết định | Vai trò |
|---|---:|---|---|---|
| R-S | 3 | Detector im lặng bao lâu trong soak 60 phút? | S2, S3; nguồn replay R-O1/R-O2 | Nghiệm thu |
| R-N | 6 | Tải hợp lệ 6–10 Mbps/client có gây báo động vô căn cứ? | S10 | Nghiệm thu |
| R-D | 10 | Độ nhạy thay đổi thế nào theo rho? | ED50, P1–P3, G1 | Nghiệm thu |
| R-C | 4 | Transient sau revert kéo dài bao lâu? | Chọn cooldown, G2 | Hiệu chỉnh |
| R-O3 | 2 | Hành động controller có tự kích hoạt detector? | S11 một phần, G3 | Nghiệm thu |
| R-O1/R-O2 | Replay | Restart và khoảng trống snapshot được xử lý thế nào? | S9, S8 | Nghiệm thu |
| R-O4 | 0 trong 6R | Twin có stale khi detector chết? | S12 trong Phase 7 | Trì hoãn |

R-C là tập hiệu chỉnh nên không được dùng để đánh giá chính cooldown được chọn
từ nó. Tổng số run được thu là 25; hai phép thử R-O chạy bằng replay và R-O4
được chuyển sang Phase 7.

## Nguồn thẩm quyền khi tài liệu mâu thuẫn

Ba mâu thuẫn được giải quyết trước khi thu dữ liệu:

1. `PHASE_6R.md` nêu 15 run, trong khi SLO niêm phong nêu 27 mục R-campaign.
   `phase6r_slo.json` là nguồn thắng; amendment 4 tách hai phép thử replay khỏi
   số run vật lý, vì vậy contract thu 25 run.
2. `PHASE_6R.md` đề xuất V1/V2, nhưng amendment 1 đã đăng ký
   `conservation_residual` và amendment 3 đóng các nhánh chưa đăng ký. Các biến
   thể V1/V2 không được đánh giá trong 6R.
3. Factor R-D ban đầu vi phạm bandwidth floor. Dãy `corrected_factors` theo rho
   trong amendment 1 là nguồn thắng và được kiểm lại bởi `ml.rcampaign.validate`.

## Gate nghiệm thu và survivorship bias

`ml.campaign.verify_run` coi `signal_present` là gate cho fault run. Điều này
phù hợp với Phase 5 nhưng sẽ loại chính các liều R-D thấp được thiết kế để có
thể không sinh tín hiệu, khiến đường liều–đáp ứng chỉ còn các run “sống sót”.

`ml.rcampaign.verify_rrun` vì vậy đổi `signal_present` thành
`covariate_signal_present` riêng cho R-D và tính lại kết quả acceptance mà không
dựa vào outcome đó. Gate dụng cụ như số tick vẫn được giữ. R-C vẫn giữ gate tín
hiệu vì một run không có transient không thể dùng để hiệu chỉnh cooldown.

## R-O split và giới hạn phát hành

- R-O1 (restart/S9) và R-O2 (gap/S8) được replay offline trên raw R-S tại các
  tick đã đăng ký.
- R-O3 thu hai run controller `admin_down`, ghi InterventionLog cả inject lẫn
  revert.
- R-O4 (kill detector/S12) chuyển sang Phase 7 vì đây là thuộc tính tích hợp
  detector–Ditto–TTL, không tồn tại trong harness 6R.

Do đó 6R chỉ đóng một phần G3 và không thể đóng G4/S12. FSM không được phát hành
cho Phase 8 trước khi Phase 7 đo S12 và S11 live.

## Hợp đồng đã khóa

- Campaign: `DT4N-P6R-RCAMPAIGN`
- Trạng thái: `planned_not_collected`
- Số run: 25
- Seed xáo thứ tự: `20260918`
- Thời gian thu ước tính: 12.995 giây, khoảng 3,6 giờ
- `design_content_sha256`:
  `3ea21c675a716723ae0289ad10490483ceb8c31e976443f3fcc791bb1514f04f`

Hash chỉ bao phủ thiết kế trong `CONTRACT_KEYS`; thời điểm ghi, validation và
provenance phụ không thuộc hash. Launcher phải dựng lại thiết kế từ module hiện
tại và amendment 1 rồi gọi integrity check trước khi chạy. Không có dữ liệu
R-campaign nào được thu trong Lesson 6R.5A.
