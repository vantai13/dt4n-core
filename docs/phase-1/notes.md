# Phase 1 — Notes (lệnh đã chạy, lỗi gặp + cách fix)


## Nghiệm thu bản Core 2026-09-15

Xem `results/report/ACCEPTANCE.md` và các log tương ứng. Bản Core kiểm chứng bằng Mininet thật, Ditto thật và namespace `org.dt4n.core`; import/test được đặt PYTHONPATH trỏ kho mới. Kết quả của phase này được tổng hợp khi suite hoàn tất, không dùng số kỳ vọng làm số đo.


### Kết quả chạy thực tế bản Core

Mạng mặc định pingAll 0% dropped (20/20); topo 5 client với spec mở rộng, bw bottleneck 2 Mbps và delay 5ms đạt 0% dropped (42/42). Normal và flood có 60 snapshot mỗi kịch bản: logs/snapshots_normal.jsonl, snapshots_flood.jsonl.

## Kiểm chứng trước ML — v2

Normal mới TCP giới hạn 2 Mbps/client, flood UDP 50 Mbps/client, luân phiên srv1/srv2. Đã thu 60 snapshot normal và 60 flood: logs/ml_normal_v2.jsonl, ml_flood_v2.jsonl. Normal có tải 8/8 link; client normal khoảng 2,15 Mbps, flood khoảng 20 Mbps. Giữ dataset v1 nguyên vẹn.
