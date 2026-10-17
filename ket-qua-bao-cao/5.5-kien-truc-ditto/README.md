# 5.5 Kiến trúc với Eclipse Ditto (ND3)

## Tệp kết quả

| Tệp | Dùng ở báo cáo |
|---|---|
| `bootstrap_scale.json` | khởi tạo Thing cho topology 22 host (20 máy khách): 52/52 Thing tạo và đọc lại được, 2,35 s lần đầu, 0,60 s lần chạy lại, không Thing nào bị tạo trùng |

Phép thử chỉ kiểm bước khởi tạo (`"scope": "bootstrap only"`), chưa đo đồng bộ hay phát hiện trên
mạng lớn. 52 Thing gồm 22 host, 3 switch, 25 link, 1 Thing đường đi và 1 Thing controller.

## Chạy lại (cần Ditto, không cần Mininet)

```bash
(cd ditto && docker compose up -d)
PYTHONPATH="$PWD" .venv/bin/python scripts/bootstrap_scale.py
```

Script tạo Thing trong namespace riêng `org.dt4n.scale`, đo hai lần, rồi xóa mọi Thing nó đã tạo.
Nó ghi đè `results/report/bootstrap_scale.json` và `results/report/topology_scale20.json`.

Danh sách 20 Thing của hệ thống thật (Bảng 3.3 của báo cáo) sinh từ `ditto/topology_spec.json`
bởi `bridge/bootstrap.py`.
