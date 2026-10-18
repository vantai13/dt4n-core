# 5.5 Mô hình dữ liệu trên Eclipse Ditto

## Tệp kết quả

| Tệp | Dùng ở báo cáo | Tệp gốc |
|---|---|---|
| `khoi-tao-thing-22-host.json` | khởi tạo Thing cho topology 22 host (20 máy khách): 52/52 Thing tạo và đọc lại được, 2,35 s lần đầu, 0,60 s lần chạy lại, không Thing nào bị tạo trùng | `results/report/bootstrap_scale.json` |

Đọc tệp: `expected_things` và `readable_things` là số Thing cần tạo và số đọc lại được;
`first_s`, `repeat_s` là thời gian khởi tạo lần đầu và lần chạy lại; `first.created` 52 và
`repeat.skipped` 52 cho thấy lần chạy lại nhận ra Thing đã có và không tạo trùng.

Phép thử chỉ kiểm bước khởi tạo (`"scope": "bootstrap only"`), chưa đo đồng bộ hay phát hiện trên
mạng lớn. 52 Thing gồm 22 host, 3 switch, 25 link, 1 Thing đường đi và 1 Thing controller.

## Chạy lại

| Script | Đo lại | Cần |
|---|---|---|
| `do_lai_khoi_tao_thing.sh` | `khoi-tao-thing-22-host.json` | Ditto đang chạy, không cần Mininet |

```bash
(cd ditto && docker compose up -d)
ket-qua-bao-cao/5.5-mo-hinh-du-lieu-ditto/do_lai_khoi_tao_thing.sh
```

Mỗi script chạy được từ bất kỳ thư mục nào. Kết quả mới ghi vào `chay-lai/<thời điểm>/` ngay trong thư mục này, cùng tên với tệp đã lưu ở trên, nên mở hai tệp cạnh nhau là so được. Kết quả đã lưu không bị đè, kể cả khi script lỗi hay bị Ctrl-C.

Script tạo Thing trong namespace riêng `org.dt4n.scale`, đo hai lần, rồi xóa mọi Thing nó đã tạo.
Đặc tả topology 22 host sinh kèm (`topology_scale20.json`) vào `chay-lai/<thời điểm>/khac/`.

Danh sách 20 Thing của hệ thống thật (Bảng 3.3 của báo cáo) sinh từ `ditto/topology_spec.json`
bởi `bridge/bootstrap.py`.
