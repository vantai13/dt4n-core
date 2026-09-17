# Phase 6R — Kết quả thí nghiệm sensor degrade

Kế hoạch và luật phán quyết đã được commit tại `8b2f4c9` trước bốn run hợp lệ.
Mỗi meta file ghi đúng commit này và `collector_unchanged=true`.

## 1. Lưu ý vận hành

Lần chạy đầu trong worktree sạch không có runtime `ditto/port_map.json`; controller
không cài route, ping log rỗng và cả bốn analyzer trả `NO_MISSING_TRAFFIC`. Các
run invalid chưa commit đã bị loại. Probe được lặp lại không đổi code hay luật,
với controller đọc port map đã đóng băng bằng đường dẫn tuyệt đối.

## 2. Kết quả bốn run hợp lệ

| Link/run | Missing bytes | Leaf drop | Backlog pre-revert | RTT pre → late | Verdict |
|---|---:|---:|---:|---:|---|
| s1-s2 04:54:44 | 2,114,095 | 0 (0%) | 2,222,040 (105.1%) | 12.1 → 2,694 ms | H1 |
| s1-s2 04:57:26 | 2,078,299 | 0 (0%) | 2,244,726 (108.0%) | 12.1 → 2,613 ms | H1 |
| s2-s3 04:56:06 | 2,896,833 | 966 (49.12%) | 1,492,204 (51.51%) | 12.1 → 9,402.5 ms | UNEXPLAINED |
| s2-s3 04:58:46 | 2,897,330 | 966 (49.11%) | 1,492,204 (51.50%) | 12.1 → 9,411 ms | UNEXPLAINED |

Ở s1-s2, cả hai lần đều có chữ ký rất mạnh của queue rồi teardown: không có
leaf drop, backlog xấp xỉ toàn bộ byte thiếu và RTT tăng hơn 200 lần.

Ở s2-s3, cơ chế là hỗn hợp gần đúng 50/50 giữa backlog và leaf drops. Do bộ luật
đăng ký trước yêu cầu riêng leaf share ≥50% cho H0, giá trị 49.11–49.12% không
đạt H0. H1 cũng không đạt vì leaf share không dưới 10%. Vì vậy verdict chính
thức vẫn là `UNEXPLAINED`, dù bảng kế toán giải thích gần như toàn bộ byte.

`other_drop_packets` trong analysis bằng leaf drop ở s2-s3 vì qdisc cha HTB
phản chiếu drop của con; không được cộng hai lần hay diễn giải thành H2 độc lập.

## 3. Kết luận được phép

Đối chứng s2-s3 không đạt H0 theo đúng ngưỡng đã niêm phong. Theo kế hoạch,
không được dùng hai verdict H1 của s1-s2 làm kết luận confirmatory về sensor.
Kết quả được ghi là bằng chứng mô tả mạnh, đồng thời cho thấy luật phân loại chưa
bao phủ cơ chế hỗn hợp nằm ngay ranh giới 50/50.

Không threshold nào được nới sau khi xem dữ liệu. Không sửa collector và không
đổi bất kỳ tham số amendment 1 nào trước R-campaign.

## 4. File bằng chứng

Mỗi run có raw JSONL 61 mẫu, meta, ping log và analysis JSON. Toàn vẹn của 16
file được ghim trong `results/probe/SHA256SUMS`.
