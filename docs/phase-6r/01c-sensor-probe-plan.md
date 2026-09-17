# Phase 6R — Thí nghiệm sensor degrade (Bước B)

## Câu hỏi

Trong run degrade s1-s2 với `ρ≈1.25`, khoảng 2.4 MB không đến đích nhưng
`lossPct=0`. Thí nghiệm này xác định lưu lượng nằm trong backlog, bị drop ở qdisc
lá, bị drop ở tầng khác, hay bị collector bỏ sót.

Đây là probe cơ chế vật lý, không phải dataset hay R-set và không đọc nhãn.

## Giả thuyết và luật phán quyết

Các ngưỡng được chốt trước khi chạy Mininet:

```text
MIN_SHARE = 0.5
MAX_LEAF_SHARE_H1 = 0.1
RTT_RATIO_H1 = 5.0
NOISE_MULT = 5.0
```

| Giả thuyết | Cơ chế | Luật |
|---|---|---|
| H0 | Sensor thấy loss | leaf giải thích ≥50% và collector drop >0 |
| H1 | Queue rồi bị hủy khi teardown | backlog ≥50%, leaf <10%, RTT tăng ≥5× |
| H2 | Drop ngoài qdisc lá | other hoặc OVS giải thích ≥50% |
| H3 | Bug collector | leaf drop >0 nhưng collector drop=0 |

Nếu byte thiếu không vượt `5 × baseline_noise × sqrt(n_ticks)`, verdict là
`NO_MISSING_TRAFFIC`. Nếu không luật nào khớp, verdict là `UNEXPLAINED`. Nhiều
cờ có thể đồng thời đúng.

## Thiết kế

- Điều kiện chính: `s1-s2`, factor `0.8274722320107196`, tái tạo Phase 6.
- Đối chứng: `s2-s3`, factor `0.82029833678748`, nơi lossPct từng thấy 27.4%.
- Mỗi điều kiện chạy ít nhất hai lần.
- Chụp qdisc ngay trước và ngay sau revert để quan sát backlog bị teardown.
- Đo qdisc leaf/parent/class, sysfs, OVS port, cân bằng byte và RTT ping.
- Dùng đúng `read_qdisc_drops`, `qdisc_interval` và hướng
  `UPSTREAM_OF_CORE` của collector hiện tại.

Đối chứng s2-s3 phải thấy H0 hoặc H0+H1. Nếu đối chứng thất bại thì không được
kết luận về s1-s2; phải sửa probe và chạy lại.

## Phương trình kế toán

```text
Σ(in - out) fault
  = backlog ngay trước revert
  + leaf qdisc drops
  + root/class/kernel/OVS drops
  + phần chưa giải thích
```

Bias nền được ước lượng ở pha pre và trừ khỏi mỗi tick. Ngưỡng nhiễu tổng dùng
`sqrt(n)` vì nhiễu cộng dồn như random walk.

## Ràng buộc

- Output ghi vào `results/probe/`, không chạm `data/phase5` hoặc `data/phase6r`.
- Luật phán quyết phải commit trước lần chạy Mininet đầu tiên.
- Không sửa collector trước R-campaign; phải giữ measurement invariance với
  collector `v3-qdisc-ratevalid` đã dùng để hiệu chỉnh envelope-1.0.0.
- Kết quả probe không được đổi R, floor, rho band hay bất kỳ tham số amendment 1.
- Probe được phép lặp vì đo cơ chế tất định, không ước lượng hiệu năng detector.
