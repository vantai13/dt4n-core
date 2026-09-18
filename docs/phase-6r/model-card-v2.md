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

## Phát hiện mở chuyển sang Phase 7

Các mục dưới đây đã được ghi nhận trong prereg nghiệm thu 6R.7 nhưng chưa được
giải quyết trong 6R. Chỉ mục `results/report/phase6r_findings_index.json` theo
dõi chúng; mã trong ngoặc là mốc tra cứu.

- **Residual bị pha loãng** (`dilution_model`). Residual đo tốc độ tích lũy hàng
  đợi chia cho tổng lưu lượng vào switch, nên độ nhạy với sự cố trên một link
  giảm theo tỷ phần lưu lượng của switch đi qua link đó. Với tải hiệu chỉnh,
  ngưỡng hiệu dụng là ρ > 1.138 trên s1-s2 và ρ > 1.319 trên s2-s3, không phải
  1.10. Phase 7 phải báo `d` theo từng link như một thuộc tính vận hành.
- **Khoảng trống độ đặc hiệu ở tải cao** (`declared_coverage_gap`). Ở 8–10
  Mbps/client, hàng đợi có thể tích lũy tạm thời và residual có thể báo. Vùng
  tải đó chỉ được phủ bởi S10, vốn là SLO chỉ báo cáo; không cổng nào đã đăng ký
  bác bỏ residual vì báo động sai ở tải cao.
- **Trạng thái offload không được ghim** (`environment_facts_not_pinned_in_sidecars`).
  GSO/TSO đổi dung lượng hàng đợi theo byte khoảng 2 lần, nên đổi thời điểm rớt
  gói. Residual đếm byte nên ít phụ thuộc biến này hơn chỉ báo mất gói. Kiểm
  `ethtool -k` trước khi so bất kỳ số drop nào với 6R.
- **s1-s2 với offload bật chưa đóng cân bằng khối lượng** (`SENSOR_CORRECT_ON_S1S2`
  bị luật vòng 2 giữ lại: closure 0.92/0.91, qlen 980/970 < 995). Không nâng cấp
  hậu nghiệm.
- **Độ lệch 11% trên s1-s2 và lỗ 8% của C1** (`C1_and_the_s1s2_misfit_cannot_both_be_innocent`).
  Mô hình pha loãng khớp s2-s3 tới 0.2% nhưng lệch +10.9% trên s1-s2, và độ lệch
  nằm trong `in − out` tính từ rate — đúng đại lượng residual dùng. Hoặc lỗ C1
  nằm ở báo cáo qdisc (residual không bị ảnh hưởng, độ lệch cần lời giải khác),
  hoặc nằm ở bộ đếm byte (residual trên s1-s2 lệch +11%). Hai khả năng loại trừ
  nhau; chưa kết luận.
- **Vùng vận hành khi phát hành** (`release_scope_restriction_not_a_new_gate`).
  Mọi nhóm có cổng của R-campaign chạy ở đúng 2 Mbps/client. Nếu
  conservation-1.0.0 được phát hành, nó chỉ được tuyên bố nghiệm thu ở tải đó;
  1–4 Mbps/client là vùng hiệu chỉnh, không phải vùng nghiệm thu.
- **Cửa sổ sau revert của F-6R4-1** (`finding_F_6R4_1_plan`). Cửa sổ inject đã
  được giải thích bằng hành lang detour; cửa sổ sau revert chưa được kiểm.

## Release gate

G3 offline PASS sau amendment 7. Phase 8 vẫn bị chặn tới khi Phase 7 chứng minh
S11 live và S12. Không được dùng receipt replay offline để bỏ qua hai gate này.

## Provenance

- Amendment: `results/report/phase6r_amendment_7.json`
- S11 FAIL lịch sử: `results/report/phase6r_replay_o3.json`
- S11 lần hai: `results/report/phase6r_replay_o3_v2.json`
- Latency hiệu chính: `results/report/phase6r_latency_v2.json`
- Receipt tổng: `results/report/phase6r_stability_v2.json`
