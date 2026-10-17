# 6.2.2 Vì sao detector bỏ sót sự cố giảm băng thông trên s1-s2

Qua s1-s2 chỉ có luồng TCP của h1 và h3 tới srv1. Khi băng thông giảm, TCP tự giảm tốc độ nên
phần lưu lượng không qua được nằm lại trong hàng đợi thay vì bị bỏ. Hai nguồn bằng chứng:

## Tệp kết quả

| Tệp | Nội dung |
|---|---|
| `gd4_s1s2_excess.json` | 5 run giảm băng thông s1-s2 của tập nghiệm thu, giây 21-39: không cột chỉ báo nào vượt biên; excess lớn nhất 0; 0; 0; 1,00; 0,28 (ρ từ 0,5 tới 2,0) so với E ≈ 5,6; h3 dưới biên dưới 12/20 giây ở ρ = 2,0; độ rộng vùng tốc độ máy khách 4,3-5,4 Mbps |
| `degrade_sensor_s1-s2_*.analysis.json` | phép thử hàng đợi với offload bật, sự cố 20 s: 0 gói bị bỏ trong 20 s, RTT từ 12,1 lên 2694 ms, phần byte thiếu nằm trong hàng đợi |
| `v2_report.json` | phép thử hàng đợi với ba điều kiện, 6 run: khi tắt offload, gói đầu tiên bị bỏ ở giây 17 của sự cố; khi giữ offload và kéo dài sự cố lên 40 s, ở giây 25; cả hai lúc hàng đợi gần đầy 1000 gói. Đối chứng trên s2-s3 (chỉ có UDP) bỏ gói từ giây 11 |

Dữ liệu thô của phép thử hàng đợi (`.jsonl`, `.meta.json`, `.ping.log`) ở `results/probe/`.

## Chạy lại

### Phân tích excess (offline)

```bash
PYTHONPATH="$PWD" .venv/bin/python scripts/tai_lap_bao_cao.py --muc 6.2.2   # so khớp, không ghi
PYTHONPATH="$PWD" .venv/bin/python scripts/gd4_s1s2_excess.py               # ghi tệp, từ chối ghi đè
```

### Phân tích lại phép thử hàng đợi từ dữ liệu thô (offline)

```bash
P=results/probe
.venv/bin/python scripts/analyze_degrade_sensor_probe.py $P/degrade_sensor_s1-s2_f0.8275_20260917T045444Z.jsonl
.venv/bin/python scripts/analyze_degrade_sensor_probe_v2.py $P/degrade_sensor_*_off*_rev*_*.jsonl
```

Hai script ghi đè tệp phân tích cạnh dữ liệu thô (`.analysis.json`, `v2_report.json`). Chạy lại
cho đúng nội dung cũ, chỉ khác dòng ghi phiên bản Python.

### Đo lại (cần testbed, root)

```bash
sudo mn -c
sudo env PYTHONPATH="$PWD" /usr/bin/python3 scripts/probe_degrade_sensor.py --link s1-s2 --factor 0.8275
sudo env PYTHONPATH="$PWD" /usr/bin/python3 scripts/probe_degrade_sensor.py --link s1-s2 --factor 0.8275 --offload off
sudo env PYTHONPATH="$PWD" /usr/bin/python3 scripts/probe_degrade_sensor.py --link s1-s2 --factor 0.8275 --revert 60
sudo env PYTHONPATH="$PWD" /usr/bin/python3 scripts/probe_degrade_sensor.py --link s2-s3 --factor 0.8203
```

Lệnh đầu ứng với phép thử offload bật. Ba lệnh sau ứng với ba điều kiện của `v2_report.json`
(tắt offload, sự cố kéo dài, đối chứng s2-s3). Mỗi lần chạy ghi một bộ tệp mới có mốc thời gian trong tên, nên không đè dữ liệu cũ.
