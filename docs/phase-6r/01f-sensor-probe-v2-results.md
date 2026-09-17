# Phase 6R — Kết quả sensor probe vòng 2

## Trình tự và môi trường

Luật, dự đoán và 7 test tổng hợp được commit/push tại `f54d850` trước khi
Mininet sinh dữ liệu. Cả sáu run ghi `git_hash=f54d8503e829df4817c28ca5e67923a1410d013d`,
`python_executable=/usr/bin/python3`, và port map
`/home/ubuntu/dt4n-core/ditto/port_map.json` có SHA-256
`d8f336e2fb153622d89833a8599c5114cb5a37a0603d2dace1ced26cb69b60e8`.
Không run nào có lỗi khi đổi offload.

## Bảng sáu run

| Điều kiện / UTC | Lớp | Drop đầu | qlen tại mẫu drop đầu | byte/skb trung vị | Leaf / collector drop | Missing byte | Backlog trước revert | Closure | Check |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| C0 `073920Z` | `QUEUE_THEN_DROP` | 31 | 1000 | 1475.20 | 967 / 969 | 2,900,457 | 1,485,134 | 1.0031 | đạt |
| C0 `074404Z` | `QUEUE_THEN_DROP` | 31 | 1000 | 1478.03 | 967 / 969 | 2,905,092 | 1,490,790 | 1.0035 | đạt |
| C1 `074047Z` | `QUEUE_THEN_DROP` | 45 | 980 | 2844.26 | 423 / 423 | 3,454,023 | 2,556,078 | 0.9221 | trượt qlen ≥ 995 |
| C1 `074531Z` | `QUEUE_THEN_DROP` | 45 | 970 | 2861.13 | 399 / 399 | 3,331,542 | 2,441,046 | 0.9108 | trượt qlen ≥ 995 |
| C2 `074237Z` | `QUEUE_THEN_DROP` | 37 | 1000 | 1492.73 | 462 / 485 | 2,166,054 | 1,492,732 | 1.0063 | đạt |
| C2 `074718Z` | `QUEUE_THEN_DROP` | 37 | 999 | 1494.16 | 495 / 496 | 2,129,642 | 1,491,344 | 1.0459 | đạt |

C0 đạt đủ hai lần nên `measurement_trusted=true`. C2 cũng đạt đủ hai lần:
trạng thái quan sát trên ba interface đều cho GSO/TSO/GRO off, kích thước skb
giảm từ khoảng 2.85 kB xuống khoảng 1.49 kB và drop xuất hiện ở tick 37 trong
cửa sổ lỗi 20 giây.

C1 thấy drop ở tick 45 trong cả hai lần và collector đếm đúng leaf drop. Tuy
nhiên, qlen tại mẫu đầu ghi nhận drop là 980 và 970, dưới ngưỡng đăng ký trước
995. Vì vậy `conclude()` không phát hành kết luận `SENSOR_CORRECT_ON_S1S2`.
Không nới ngưỡng hoặc chấm lại sau khi xem dữ liệu. Raw cho thấy từ tick 44
sang 45, drop tăng 0→39 và 0→48 trong khi qlen lần lượt là 980 và 970; đây là
kết quả cần giữ nguyên để phân tích sau, không phải lý do sửa luật vòng 2.

## Verdict đăng ký trước

```json
{
  "measurement_trusted": true,
  "conclusions": [
    "GSO_EXPLAINS_DELAYED_DROP: tat offload -> drop trong 20 s"
  ]
}
```

Kết luận chính thức: phép đo đáng tin, và việc tắt offload làm drop xuất hiện
trong cửa sổ 20 giây đúng như dự đoán. Kết luận riêng về C1 không đạt vì check
qlen nghiêm ngặt, dù bằng chứng mô tả cho thấy collector đã quan sát drop trên
s1-s2 ở cả C1 lẫn C2.

## Toàn vẹn và ràng buộc

`results/probe/SHA256SUMS_V2` niêm phong 25 artifact: sáu raw JSONL, sáu ping
log, sáu meta, sáu analysis và báo cáo tổng. `sha256sum -c` đạt 25/25. Collector
và amendment 1 không thay đổi; kết quả này không được dùng để đổi threshold
trước R-campaign.

## Quy tắc dừng

Dừng probe cơ chế tại vòng 2, không viết luật v3 rồi lặp đến khi C1 đạt. C0 đã
xác nhận công cụ đo, C2 đã xác nhận GSO làm drop đến muộn, và collector thấy
drop trong 6/6 run. Một vòng mới không thay đổi quyết định kỹ thuật nào: không
sửa collector trước R-campaign và không đổi amendment 1. Chạy tiếp chỉ để đạt
một nhãn kết luận sẽ tạo optional stopping; trạng thái C1 được giữ là “ủng hộ
mạnh nhưng chưa xác nhận theo luật đăng ký trước”.
