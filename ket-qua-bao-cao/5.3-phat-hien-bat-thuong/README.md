# 5.3 Phát hiện bất thường (ND2)

Mọi kết quả ở mục này là của một mô hình detector duy nhất (phiên bản 2.1.0), học trên tám run
huấn luyện và cố định trước khi thu tập nghiệm thu (Mục 3.4 và 4.3 của báo cáo).

Thứ tự đọc: `mo-hinh/` (mô hình học được gì) → `tieu-chi-ghi-truoc/` (đạt là thế nào, ghi trước
khi đo) → `tap-phat-trien/` (Bảng 5.2, 5.3) → `tap-nghiem-thu/` (Bảng 5.4, 5.5).

Các tệp JSON ở đây phần lớn có dạng `{"content": {...}, "content_sha256": "..."}`. Dữ liệu nằm
trong `content`, còn `content_sha256` là mã băm của chính phần đó, dùng để kiểm tệp không bị sửa.

## `mo-hinh/`: mô hình

| Tệp | Nội dung | Tệp gốc |
|---|---|---|
| `envelope-2.1.0.json` | biên min/max của 71 cột (`content.bounds`), ngưỡng K = 18, E ≈ 5,609 (`content.thresholds.primary`) | `models/envelope-2.1.0.json` |
| `detector-release-2.1.0.json` | bản phát hành detector: envelope, residual, FSM (`content.fsm_params`), bộ chặn vùng tải | `models/detector-release-2.1.0.json` |
| `bang-bao-toan-residual.json` | bảng bảo toàn lưu lượng dùng cho kênh residual, ngưỡng R ≈ 0,0753 (`content.calibration.R`) | `results/report/gd4_conservation.json` |
| `bien-ban-hoc-lai.json` | biên bản học: tám run dùng để học (`content.train_run_ids`), K, E, R, ngưỡng vùng vận hành | `results/report/gd4_retrain.json` |
| `ma-bam-du-lieu-huan-luyen.json` | mã băm của dữ liệu huấn luyện và commit đã thu | `results/report/gd4_manifest.json` |

## `tieu-chi-ghi-truoc/`: chỉ tiêu ghi trước khi thu tập nghiệm thu

| Tệp | Nội dung | Tệp gốc |
|---|---|---|
| `tieu-chi-nghiem-thu.json` | chỉ tiêu S1, S2, S4, mức mục tiêu, cách chấm, cam kết báo kết quả dù tốt hay xấu | `results/report/gd4_acceptance_prereg.json` |
| `tieu-chi-nghiem-thu.md` | cùng nội dung, viết thành văn | `results/gd4/prereg.md` |

## `tap-phat-trien/`: Bảng 5.2 và 5.3

| Tệp | Nội dung | Tệp gốc |
|---|---|---|
| `excess-dual-va-iforest.json` | so sánh hai luật excess, dual và Isolation Forest trên phần kiểm tra của tập phát triển | `results/report/gd4_devset.json` |

Đọc tệp (bản 2.1 nằm ở các khóa `v21`, khóa `v1` là bản 1.0.0 cũ để đối chiếu):

| Trường | Giá trị |
|---|---|
| `content.envelope.v21.secondary_excess.tp` / `n_positive` | 137/160 giây có sự cố được phát hiện |
| `content.envelope.v21.secondary_excess.fp` / `n_negative` | 23/430 giây bình thường bị báo nhầm |
| `content.envelope.v21.secondary_excess.recall_by_fault` | tỉ lệ phát hiện theo loại sự cố |
| `content.envelope.v21.secondary_excess.positions` | báo nhầm nằm ở đâu: 0 ở run bình thường, 0 trước giây 21, dồn ở giây 41-47 |
| `content.envelope.v21.secondary_dual` | như trên cho luật dual: 127/160 và 5/430 |
| `content.iforest.v21.recall_mean`, `fpr_mean` | Isolation Forest: 0 trên cả 5 lần học, báo nhầm trung bình 0,0056 |

## `tap-nghiem-thu/`: Bảng 5.4, 5.5 và các đoạn sau bảng

| Tệp | Nội dung | Tệp gốc |
|---|---|---|
| `cau-hinh-25-run.json` | cấu hình từng run (`runs[]`), nhóm run (`groups`): RD giảm băng thông, RC flood và dịch nút cổ chai, RN tải cao, RS chạy nền | `results/report/gd4r_contract.json` |
| `ma-bam-du-lieu-nghiem-thu.json` | mã băm dữ liệu từng run, số run đã thu (24/25) | `results/report/gd4r_manifest.json` |
| `cham-giam-bang-thong-flood-tai-cao.json` | chấm nhóm RD, RC, RN. Riêng run `RN-load8M-s5014-r2` lấy ở tệp kế tiếp | `results/report/gd4_acceptance_v21.json` |
| `cham-lai-mot-run-tai-cao.json` | chấm lại run tải cao `RN-load8M-s5014-r2` sau khi thu lại | `results/report/gd4_acceptance_v21_rn_retry.json` |
| `cham-chay-nen-2-gio.json` | 2 run chạy nền 60 phút | `results/report/gd4_acceptance_v21_rs.json` |

Đọc tệp chấm (cả ba tệp `cham-*` cùng cấu trúc, kết luận nằm ở `content.verdicts`):

| Trường | Chỉ tiêu | Giá trị |
|---|---|---|
| `verdicts.S1.value` | tỉ lệ sự cố giảm băng thông được phát hiện, mục tiêu ≥ 0,875 | 0,40, `FAIL` |
| `verdicts.S1.by_rho` | tách theo mức giảm ρ | |
| `verdicts.S4.value_ms` | thời gian phát hiện lớn nhất, mục tiêu ≤ 3000 ms | 20 000 ms, `FAIL` |
| `verdicts.S4.all_values` | thời gian phát hiện từng sự cố | |
| `verdicts.RC_descriptive` | 4 run flood và dịch nút cổ chai | 4/4 phát hiện |
| `verdicts.S10` | báo động ở run tải cao, trước khi áp bộ chặn vùng tải | |
| `verdicts.operational_guard.per_run.<run>.combined.published_alarm_ticks` | số giây còn báo động sau khi áp bộ chặn vùng tải; báo cáo xét 6 run `RN-*` | 0 ở cả 6 run (run `RN-load8M-s5014-r2` lấy ở `cham-lai-mot-run-tai-cao.json`) |
| `verdicts.S2.value` (chỉ ở `cham-chay-nen-2-gio.json`) | cận trên 95% số báo động sai mỗi giờ, mục tiêu ≤ 3 | 1,50 lần/giờ trên 2,0 giờ, `PASS` |

Trong `cham-giam-bang-thong-flood-tai-cao.json`, S2 ghi `PENDING` vì lượt chấm đó chưa có nhóm chạy nền.

## Chạy lại

| Script | Làm gì | Cần |
|---|---|---|
| `kiem_tra_offline.sh` | tính lại mọi con số của Mục 3.4 và 5.3 từ dữ liệu thô, in KHỚP hoặc LỆCH; không ghi tệp | offline, khoảng 1 phút |
| `cham_lai_tap_nghiem_thu.sh` | chấm lại detector 2.1 trên tập nghiệm thu, ghi `cham-RD-RC-RN.json` và `cham-RS.json` | offline, vài giây |

```bash
ket-qua-bao-cao/5.3-phat-hien-bat-thuong/kiem_tra_offline.sh
```

Mỗi script chạy được từ bất kỳ thư mục nào. Kết quả mới ghi vào `chay-lai/<thời điểm>/` ngay trong thư mục này, cùng tên với tệp đã lưu ở trên, nên mở hai tệp cạnh nhau là so được. Kết quả đã lưu không bị đè, kể cả khi script lỗi hay bị Ctrl-C.

Hai tệp do `cham_lai_tap_nghiem_thu.sh` ghi có cùng cấu trúc với các tệp `cham-*.json` ở trên.
Dữ liệu của run `RN-load8M-s5014-r2` hiện là bản thu lại, nên `cham-RD-RC-RN.json` ứng với
`cham-giam-bang-thong-flood-tai-cao.json` và `cham-lai-mot-run-tai-cao.json` gộp lại.

`scripts/gd4_devset.py` (tập phát triển) và `python -m ml.gd4_retrain build` (học mô hình) ghi
vào `results/report/` và `models/`, nên từ chối chạy khi tệp đã có. `kiem_tra_offline.sh` chạy lại
đúng code của chúng mà không ghi gì.

### Thu lại dữ liệu (cần testbed, không có script riêng)

```bash
sudo mn -c
export DT4N_RYU=$(which ryu-manager)     # nếu Ryu không ở đường dẫn mặc định
PYTHONPATH="$PWD" .venv/bin/python scripts/launch_ml_dataset.py --campaign gd4r --only RD-degrade-s1-s2-rho200-s5101-r1   # một run
PYTHONPATH="$PWD" .venv/bin/python scripts/launch_ml_dataset.py --campaign gd4r                 # cả tập
```

`--campaign gd4` thu run huấn luyện, `--campaign gd4r` thu tập nghiệm thu. Tên run lấy trong
`tap-nghiem-thu/cau-hinh-25-run.json` (khóa `runs[].run_id`). Dữ liệu ghi vào `data/phase5/gd4r/`.
Hai cấu hình thu này ghi tên máy `dt4n-research-01`, từ chối chạy trên máy khác và bỏ qua run đã
có dữ liệu; xem lưu ý ở [README của thư mục](../README.md#hai-lưu-ý-khi-chạy-lại). Launcher cần
`sudo -n` chạy được không hỏi mật khẩu, vì runner Mininet chạy dưới quyền root.
