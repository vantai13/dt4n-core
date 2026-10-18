# Danh mục script

Thư mục này có 66 script, trong đó 28 script dùng trực tiếp cho báo cáo (mục 1 và 2 bên dưới).

**Muốn chạy lại một kết quả của báo cáo, đừng gọi script ở đây mà dùng script trong thư mục của
mục đó trong [ket-qua-bao-cao/](../ket-qua-bao-cao/README.md#mọi-script-chạy-lại).** Các script ở
đó gọi script ở đây, nhưng ghi kết quả mới ra thư mục riêng và không đè kết quả đã lưu. Phần còn lại
thuộc các giai đoạn phát triển trước và được giữ nguyên tên, nguyên chỗ, vì một trong hai lý do:

- được script của báo cáo import (ghi rõ ở cột "Dùng bởi" bên dưới);
- bị ghim mã băm theo đường dẫn trong các tệp tiêu chí ghi trước (`results/report/*prereg*.json`,
  `*amendment*.json`, ...). Đổi tên hay chuyển chỗ sẽ làm hỏng phép kiểm toàn vẹn
  (`test/test_amendment_pin_ledger.py`).

Ký hiệu cột "Cần": **offline** chỉ cần `.venv`; **testbed** cần Mininet, Ryu, Ditto và sudo không
hỏi mật khẩu; **Ditto** chỉ cần Ditto.

## 1. Lệnh chung

| Script | Làm gì | Cần |
|---|---|---|
| `tai_lap_bao_cao.py` | tính lại mọi con số offline của báo cáo và so khớp tuyệt đối với kết quả đã lưu, không ghi tệp nào | offline |
| `kiem_tra_moi_truong.py` | kiểm thư viện, dữ liệu; thêm `--testbed` để kiểm sudo, Mininet, Ryu, Ditto | offline |
| `dong_bo_ket_qua_bao_cao.py` | chép tệp kết quả gốc vào `ket-qua-bao-cao/` với tên đọc được; `--check` để kiểm | offline |
| `xuat_csv_du_lieu.py` | xuất dữ liệu huấn luyện, tập phát triển, tập kiểm tra độc lập thành CSV với 71 cột của detector; `--check` để kiểm | offline |
| `chay_lai_muc.py` | chạy một lệnh mà không đè kết quả đã lưu: gom tệp lệnh ghi ra vào `ket-qua-bao-cao/<mục>/chay-lai/`, rồi trả tệp cũ về | |

## 2. Theo mục báo cáo

### 5.1 Phản chiếu trạng thái và 5.2 Điều khiển từ xa

Hai mục này dùng chung hai launcher. Cả hai **ghi đè `results/report/`**, nên hãy chạy trên bản clone riêng.

| Script | Làm gì | Ghi ra | Cần |
|---|---|---|---|
| `launch_ml_preflight.py` | bật Ryu rồi gọi `run_ml_preflight.py` dưới quyền root | | testbed |
| `run_ml_preflight.py` | đo độ trễ đồng bộ lên và độ trễ lệnh (30 lần mỗi loại, thời điểm ngẫu nhiên), phép thử HTTP 408; trước đó thu thêm dữ liệu ML không dùng trong báo cáo | `latency_up_randomized.json`, `latency_command_randomized.json`, `command_ack_timeout3.json` | testbed |
| `run_network_suite.py` | bật Ryu rồi gọi `run_acceptance.py` | | testbed |
| `run_acceptance.py` | đối chiếu thực thể, 20 lần tắt link, 60 lệnh đo từng chặng, chạy liên tục 30 phút | `verification.json`, `command_flow.json`, `soak_30min.json` | testbed |

Code đo nằm ở `measurements/`: `measure_latency.py` (đồng bộ lên), `measure_command_latency.py`
(độ trễ lệnh), `measure_command_flow.py` và `trace_latency.py` (từng chặng của lệnh).

### 3.4 Học detector và 5.3 Phát hiện bất thường

| Script | Làm gì | Cần |
|---|---|---|
| `launch_ml_dataset.py` | thu dữ liệu: `--campaign gd4` run huấn luyện, `--campaign gd4r` tập kiểm tra độc lập; bật Ryu rồi gọi `generate_ml_dataset.py` | testbed |
| `generate_ml_dataset.py` | chạy từng run của cấu hình thu (không gọi trực tiếp) | testbed |
| `build_gd4_prereg.py` | ghi mức đặt trước của detector 2.1 trước khi thu tập kiểm tra độc lập | offline |
| `declare_gd4_drift.py` | khai báo hai tệp đã ghim bị đổi giữa chừng, để phép kiểm toàn vẹn ghi nhận lý do | offline |
| `gd4_devset.py` | Bảng 5.2, 5.3: excess, dual, Isolation Forest trên tập phát triển | offline |
| `gd4_score.py` | Bảng 5.4, 5.5: chấm detector trên tập kiểm tra độc lập, theo nhóm run | offline |

Học lại mô hình không nằm ở đây mà ở `python -m ml.gd4_retrain build`.

### 5.3.3 Sự cố trên link chỉ có lưu lượng TCP

| Script | Làm gì | Cần |
|---|---|---|
| `gd4_s1s2_excess.py` | excess của detector 2.1 trên 5 run giảm băng thông s1-s2 | offline |
| `probe_degrade_sensor.py` | phép thử hàng đợi: giảm băng thông một link, ghi số đo từng giây | testbed |
| `analyze_degrade_sensor_probe.py` | phân tích phép thử hàng đợi, lượt 1 | offline |
| `analyze_degrade_sensor_probe_v2.py` | phân tích phép thử hàng đợi, lượt 2 (ba điều kiện) | offline |

### 5.5 Mô hình dữ liệu trên Eclipse Ditto

| Script | Làm gì | Cần |
|---|---|---|
| `bootstrap_scale.py` | tạo 52 Thing cho topology 22 host, đo hai lần, rồi xóa | Ditto |

### 5.6 Tự động hóa tài nguyên đám mây

Không có script ở đây. Mọi lệnh nằm trong gói `cloud/` (`python3 -m cloud.experiment ...`), xem
[README của mục](../ket-qua-bao-cao/5.6-tu-dong-hoa-aws/README.md).

### 5.7 Vòng kín

| Script | Làm gì | Cần |
|---|---|---|
| `chay_vong_kin.sh` | kiểm môi trường, bật Ryu, chạy A/B rồi phép thử định vị, ghi vào thư mục mới; được `ket-qua-bao-cao/5.7-vong-kin/do_lai_tren_testbed.sh` gọi | testbed |
| `chay_lai_vong_kin.py` | được `chay_vong_kin.sh` gọi, ghi receipt ra chỗ khác thay vì `results/report/` | testbed |
| `build_gd4cl_prereg.py` | ghi luật, thiết kế, tiêu chí của thí nghiệm vòng kín trước khi chạy | offline |
| `gd4cl_common.py` | luật chọn ứng viên theo chiều, dùng chung | |
| `gd4cl_offline_check.py` | chạy luật chọn ứng viên offline trên 30 run đã có | offline |
| `run_gd4cl_ab.py` | A/B bảo vệ, ghi `gd4cl_ab.json` | testbed |
| `run_gd4cl_dinh_vi.py` | phép thử định vị, ghi `gd4cl_c1.json` | testbed |
| `run_gd4cl_c1.py` | phần lõi của phép thử định vị, được `run_gd4cl_dinh_vi.py` gọi | |

## 3. Giai đoạn trước, không dùng cho báo cáo

Không cần các script này để tái lập báo cáo. Chúng không được bảo trì và có thể không chạy được
nữa. Script nào được script của báo cáo import thì ghi ở cột "Dùng bởi".

| Giai đoạn | Script | Dùng bởi |
|---|---|---|
| Phase 5 (dữ liệu ML) | `build_matrix.py`, `analyze_ml_preflight.py` | |
| Phase 6 (envelope, Isolation Forest) | `run_phase6_envelope.py`, `run_phase6_iforest.py` | `gd4_devset.py` |
| | `build_model_artifact.py` | |
| Phase 6R (đánh giá lại detector 1.0.0) | `run_phase6r_acceptance.py` | `gd4_score.py` |
| | `build_phase6r_amendment1.py`, `build_phase6r_amendment2.py`, `build_phase6r_amendment3.py`, `build_phase6r_amendment4.py`, `build_phase6r_amendment6.py`, `build_phase6r_amendment7.py`, `build_phase6r_amendment8.py`, `build_phase6r_stability_prereg.py`, `build_detector_release.py`, `replay_phase6r_fsm.py`, `replay_phase6r_s11_v2.py`, `replay_phase6r_stability.py`, `rehearse_acceptance.py`, `measure_phase6r_latency.py`, `measure_phase6r_latency_v2.py`, `soak_phase6r_detector.py`, `measure_tick_jitter.py`, `diag_phase6r_residual_onset.py`, `diag_s11_suppression.py` | |
| Phase 7 (detector chạy trực tiếp) | `phase7_live_common.py` | `run_gd4cl_ab.py`, `run_gd4cl_c1.py` |
| | `measure_phase7_e2e.py`, `measure_phase7_s12_live.py`, `run_phase7_contention.py`, `run_phase7_s11_live.py`, `soak_phase7_live_v2.py` | |
| Phase 8 (vòng kín với detector 1.0.0) | `phase8_ab_common.py` | `run_gd4cl_ab.py`, `run_gd4cl_c1.py` |
| | `phase8_infra_health.py` | `run_gd4cl_c1.py`, `run_gd4cl_dinh_vi.py` |
| | `run_phase8_c1_control.py` | `run_gd4cl_c1.py` |
| | `phase8_replay.py`, `probe_phase8_actionability.py`, `probe_phase8_localization.py`, `run_phase8_s11_bw.py` | |

Tài liệu của các giai đoạn này ở `archive/docs/`.
