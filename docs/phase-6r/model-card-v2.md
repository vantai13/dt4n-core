# Model card v2 — DT4N envelope detector sau Amendment 7

Tài liệu này bổ sung, không thay thế, model card Phase 6. Các metric hiệu quả
S1/S2/S3/S4/S7/S10 vẫn chờ nghiệm thu 6R.7; nhãn chưa được mở.

## Đường vận hành

Phase 7 dùng `FastOnlineScorer`. Trên harness detector-only, p95 của đường
`observe() + step()` là 0,943 ms và cold start scored đầu tiên là 0,996 ms.
`OnlineScorer` là oracle tham chiếu, p95 56,249 ms và không đạt S5 50 ms.

RSS nền đã quan sát khoảng 566 MiB, phần lớn từ stack Python khoa học. S6 chỉ
chứng minh mức tăng 30 phút là 0,2852 MiB; nó không đặt ngân sách cho RSS nền
và không chứng minh ổn định nhiều giờ.

## Cơ chế intervention

Intervention controller là khoảng `[inject, revert + cooldown)`, không còn là
hai sự kiện điểm độc lập. Với `admin_down`, blast radius gồm radius tuyến gốc
và hành lang switch detour ngắn nhất khi bỏ link mục tiêu. Điều kiện suppression
vẫn là toàn bộ entity vi phạm cục bộ phải nằm trong radius.

Inject không có revert dùng lease tối đa 120 giây. Khi lease hết, suppression
dừng và transition mang `cause=stale_intervention`; hệ fail noisy thay vì im
lặng vô hạn.

## Failure modes và trade-off bắt buộc

1. Một sự cố thật, độc lập, xảy ra trên intervention/detour corridor trong lúc
   khoảng đang mở có thể bị suppression. Đây là giá phải trả đã biết để phá
   vòng phản hồi dương, không phải tín hiệu được phép bỏ qua trong review.
2. Detour được suy ra từ routing table đóng băng. Nếu topology/routing runtime
   khác artifact, radius có thể thiếu hoặc thừa; runtime phải kiểm SHA routing.
3. Lease 120 giây ưu tiên fail-safe. Một intervention hợp lệ dài hơn lease sẽ
   phát alarm trở lại và `stale_intervention`, gây ồn nhưng tránh mù vĩnh viễn.
4. S11 v2 chỉ PASS trên controller harness repeatable: 0 act entry và 21 tick
   suppression trên mỗi run. Nó chưa thay thế S11 live của Phase 7.
5. Latency detector-only không bao gồm tranh chấp CPU từ Mininet, Ryu, Ditto,
   MongoDB, nginx hoặc dashboard.

## Release gate

G3 offline PASS sau amendment 7. Phase 8 vẫn bị chặn tới khi Phase 7 chứng minh
S11 live và S12. Không được dùng receipt replay offline để bỏ qua hai gate này.

## Provenance

- Amendment: `results/report/phase6r_amendment_7.json`
- S11 FAIL lịch sử: `results/report/phase6r_replay_o3.json`
- S11 lần hai: `results/report/phase6r_replay_o3_v2.json`
- Latency hiệu chính: `results/report/phase6r_latency_v2.json`
- Receipt tổng: `results/report/phase6r_stability_v2.json`
