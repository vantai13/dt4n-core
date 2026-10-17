# 5.3 Phát hiện bất thường (ND2)

Mọi kết quả ở mục này là của một mô hình detector duy nhất (phiên bản 2.1.0), học trên tám run
huấn luyện và cố định trước khi thu tập nghiệm thu (Mục 3.4 và 4.3 của báo cáo).

## Tệp kết quả

### `mo-hinh/`: mô hình

| Tệp | Nội dung |
|---|---|
| `envelope-2.1.0.json` | biên min/max từng cột, K = 18, E ≈ 5,609 |
| `detector-release-2.1.0.json` | bản phát hành detector: envelope, residual (R ≈ 0,0753), FSM, bộ chặn vùng tải |
| `gd4_conservation.json` | bảng bảo toàn dùng cho kênh residual |
| `gd4_retrain.json` | biên bản học: run dùng để học, các tham số học được (K, E, R, ngưỡng vùng vận hành) |
| `gd4_manifest.json` | mã băm của dữ liệu huấn luyện |

### `tap-phat-trien/`: Bảng 5.2 và 5.3 của báo cáo

| Tệp | Nội dung |
|---|---|
| `gd4_devset.json` | excess 137/160 giây đúng, 23/430 báo nhầm; dual 127/160 và 5/430; Isolation Forest 0 trên cả 5 lần học; số giây theo loại sự cố |

### `tap-nghiem-thu/`: Bảng 5.4, 5.5 và các đoạn sau bảng

| Tệp | Nội dung |
|---|---|
| `gd4r_contract.json`, `gd4r_manifest.json` | cấu hình từng run của tập nghiệm thu và mã băm dữ liệu |
| `gd4_acceptance_v21.json` | chấm các nhóm R-D (10 run giảm băng thông), R-C (4 run flood, dịch nút cổ chai) và R-N (6 run tải cao): S1 = 0,40, thời gian lớn nhất 20,0 s, R-C 4/4. Riêng run `RN-load8M-s5014-r2` dùng kết quả ở tệp kế tiếp |
| `gd4_acceptance_v21_rn_retry.json` | chấm run tải cao `RN-load8M-s5014-r2` |
| `gd4_acceptance_v21_rs.json` | 2 run chạy nền 60 phút: 0 báo động sai, cận trên 1,50 lần/giờ |

### `tieu-chi-ghi-truoc/`

| Tệp | Nội dung |
|---|---|
| `gd4_acceptance_prereg.json`, `prereg.md` | chỉ tiêu, mức mục tiêu và cách chấm, ghi trước khi thu tập nghiệm thu |

## Chạy lại

### Tính lại mọi con số (offline)

```bash
export PYTHONPATH="$PWD"
.venv/bin/python scripts/tai_lap_bao_cao.py --muc 3.4   # học lại, so với mô hình đã lưu
.venv/bin/python scripts/tai_lap_bao_cao.py --muc 5.3   # tập phát triển và tập nghiệm thu
```

### Chấm riêng từng phần (offline, ghi ra tệp mới)

```bash
export PYTHONPATH="$PWD"
R=models/detector-release-2.1.0.json

# tập nghiệm thu, theo nhóm
.venv/bin/python scripts/gd4_score.py --release $R --set gd4r --groups RD RC RN --out /tmp/rd_rc_rn.json
.venv/bin/python scripts/gd4_score.py --release $R --set gd4r --groups RS --out /tmp/rs.json
```

Trong tệp ra, `verdicts.S1`, `verdicts.S2`, `verdicts.S4` là ba chỉ tiêu của Bảng 5.4;
`verdicts.S4.all_values` là thời gian phát hiện từng sự cố; `verdicts.S10` và
`verdicts.operational_guard` là kết quả tải cao trước và sau khi áp bộ chặn vùng tải.

`scripts/gd4_devset.py` (tập phát triển) và `python -m ml.gd4_retrain build` (học mô hình) ghi
vào `results/report/` và `models/`, nên từ chối chạy khi tệp đã có. Để kiểm mà không ghi gì,
dùng `tai_lap_bao_cao.py` như trên.

### Thu lại dữ liệu (cần testbed)

```bash
sudo mn -c
export DT4N_RYU=$(which ryu-manager)     # nếu Ryu không ở đường dẫn mặc định
PYTHONPATH="$PWD" .venv/bin/python scripts/launch_ml_dataset.py --campaign gd4r --only RD-degrade-s1-s2-rho200-s5101-r1   # một run
PYTHONPATH="$PWD" .venv/bin/python scripts/launch_ml_dataset.py --campaign gd4r                 # cả tập
```

`--campaign gd4` thu run huấn luyện, `--campaign gd4r` thu tập nghiệm thu. Tên run lấy trong
`results/report/gd4r_contract.json`. Hai cấu hình thu này ghi tên máy `dt4n-research-01`, từ
chối chạy trên máy khác và bỏ qua run đã có dữ liệu; xem lưu ý ở
[README của thư mục](../README.md#hai-lưu-ý-khi-chạy-lại). Launcher cần `sudo -n` chạy được
không hỏi mật khẩu, vì runner Mininet chạy dưới quyền root.
