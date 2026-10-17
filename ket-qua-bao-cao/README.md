# Kết quả theo từng mục của báo cáo

Mỗi thư mục con ứng với một mục trong Chương 5 và 6 của báo cáo. Trong mỗi thư mục có:

- bản sao các tệp kết quả của mục đó, **đặt tên theo nội dung** (ví dụ `do-tre-lenh.json`);
- các **script chạy lại** của mục đó (`kiem_tra_offline.sh`, `do_lai_*.sh`, ...);
- `README.md` nói tệp nào cho ra bảng hay hình nào, con số nằm ở trường nào trong tệp, tệp gốc
  ở đâu, và script nào chạy lại phần nào;
- sau khi chạy lại: thư mục `chay-lai/<thời điểm>/` chứa kết quả mới, cùng tên với tệp đã lưu.

```
5.2-dieu-khien-tu-xa/
├── README.md                        đọc trước
├── do-tre-lenh.json                 kết quả đã lưu, dùng trong báo cáo
├── thoi-gian-tung-chang.json
├── phan-hoi-ditto-408.json
├── do_lai_do_tre_lenh.sh            đo lại do-tre-lenh.json, phan-hoi-ditto-408.json
├── do_lai_thoi_gian_tung_chang.sh   đo lại thoi-gian-tung-chang.json
└── chay-lai/20261017T081231Z/       kết quả mới sau mỗi lần chạy lại (không đưa vào git)
    ├── do-tre-lenh.json
    └── phan-hoi-ditto-408.json
```

Bản sao giống tệp gốc từng byte, chỉ khác tên. Tệp gốc vẫn ở `results/`, `models/`, với tên cũ,
vì các script đọc và ghi ở đó, và nhiều tệp tiêu chí ghi trước đã ghim mã băm theo đường dẫn gốc.
Bảng tra tên ở [cuối trang](#tên-bản-sao-và-tệp-gốc).

## Ba mức chạy lại

| Mức | Cần gì | Dùng cho |
|---|---|---|
| Offline | môi trường `.venv` (xem [README chính](../README.md#tải-về-và-cài-đặt)) | chấm điểm detector, học lại mô hình, what-if hồi cứu, các phân tích |
| Testbed | Linux có root, Mininet, Open vSwitch, Ryu, Ditto chạy bằng Docker | đo độ trễ, thu dữ liệu, kiểm mù what-if, vòng kín |
| AWS | thêm tài khoản AWS (có chi phí) | tự động hóa đám mây |

## Kiểm nhanh mọi con số offline

```bash
ket-qua-bao-cao/kiem_tra_tat_ca.sh      # mọi mục, khoảng 1 phút
```

Script không ghi tệp nào. Nó tính lại từ dữ liệu thô bằng đúng code đã dùng, so khớp tuyệt đối với
tệp kết quả đã lưu và in `KHỚP` hoặc `LỆCH` cho từng mục, rồi kiểm các bản sao trong thư mục này
còn giống tệp gốc. Muốn kiểm một mục, chạy `kiem_tra_offline.sh` trong thư mục của mục đó.

## Mọi script chạy lại

Chạy được từ bất kỳ thư mục nào. Kết quả đã lưu không bị đè, kể cả khi script lỗi hay bị Ctrl-C.

| Mục | Script | Làm gì | Cần |
|---|---|---|---|
| tất cả | `kiem_tra_tat_ca.sh` | tính lại mọi con số offline, kiểm bản sao | offline |
| 5.1 | `5.1-phan-chieu-trang-thai/do_lai_do_tre_dong_bo_len.sh` | độ trễ đồng bộ lên (kèm độ trễ lệnh, HTTP 408 của 5.2) | testbed |
| 5.1 | `5.1-phan-chieu-trang-thai/do_lai_doi_chieu_va_chay_30_phut.sh` | đối chiếu, 20 lần tắt link, chạy 30 phút (kèm từng chặng của 5.2) | testbed |
| 5.2 | `5.2-dieu-khien-tu-xa/do_lai_do_tre_lenh.sh` | độ trễ lệnh, HTTP 408 (cùng lần chạy với script đầu của 5.1) | testbed |
| 5.2 | `5.2-dieu-khien-tu-xa/do_lai_thoi_gian_tung_chang.sh` | thời gian từng chặng (cùng lần chạy với script thứ hai của 5.1) | testbed |
| 3.4, 5.3 | `5.3-phat-hien-bat-thuong/kiem_tra_offline.sh` | học lại mô hình, tập phát triển, tập nghiệm thu: so khớp | offline |
| 5.3 | `5.3-phat-hien-bat-thuong/cham_lai_tap_nghiem_thu.sh` | chấm lại tập nghiệm thu ra tệp mới | offline |
| 5.4 | `5.4-what-if/kiem_tra_offline.sh` | kiểm hồi cứu what-if | offline |
| 5.5 | `5.5-kien-truc-ditto/do_lai_khoi_tao_thing.sh` | khởi tạo 52 Thing | Ditto |
| 5.7 | `5.7-vong-kin/kiem_tra_offline.sh` | luật chọn ứng viên: so khớp, bộ test | offline |
| 5.7 | `5.7-vong-kin/do_lai_tren_testbed.sh [ab\|c1]` | A/B bảo vệ, phép thử định vị | testbed |
| 6.2.2 | `6.2.2-co-che-bo-sot-s1-s2/kiem_tra_offline.sh` | excess trên 5 run s1-s2: so khớp | offline |
| 6.2.2 | `6.2.2-co-che-bo-sot-s1-s2/phan_tich_lai_hang_doi.sh` | phân tích lại phép thử hàng đợi | offline |
| 6.2.2 | `6.2.2-co-che-bo-sot-s1-s2/do_lai_thu_hang_doi.sh` | đo lại phép thử hàng đợi | testbed |
| hình | `hinh-va-bang/ve_lai.sh` | vẽ lại Hình 5.1, 5.2, sinh lại Bảng 5.6 | offline |

Mục 5.6 (AWS) và phép kiểm mù của 5.4 không có script một lệnh, vì phải làm từng bước bằng tay;
README của hai mục đó ghi từng bước.

Các script dùng chung `_chung.sh` và `scripts/chay_lai_muc.py`. `chay_lai_muc.py` chụp lại `results/`
trước khi chạy, gom tệp mà lệnh ghi ra vào `chay-lai/<thời điểm>/` của đúng mục với tên đọc được,
rồi trả tệp cũ về.

## Bản đồ mục báo cáo

| Mục báo cáo | Thư mục | Nội dung | Mức chạy lại |
|---|---|---|---|
| 5.1 Phản chiếu trạng thái mạng (ND1) | [5.1-phan-chieu-trang-thai](5.1-phan-chieu-trang-thai/) | đối chiếu thực thể, 20 lần tắt link, độ trễ đồng bộ, chạy 30 phút | testbed |
| 5.2 Điều khiển từ xa (ND2) | [5.2-dieu-khien-tu-xa](5.2-dieu-khien-tu-xa/) | độ trễ lệnh, thời gian từng chặng, HTTP 408 | testbed |
| 5.3 Phát hiện bất thường (ND2) | [5.3-phat-hien-bat-thuong](5.3-phat-hien-bat-thuong/) | mô hình, tập phát triển, tập nghiệm thu, tiêu chí ghi trước | offline (chấm), testbed (thu dữ liệu) |
| 5.4 Phân tích what-if (MT2) | [5.4-what-if](5.4-what-if/) | kiểm hồi cứu, kiểm mù | offline, testbed |
| 5.5 Kiến trúc với Ditto (ND3) | [5.5-kien-truc-ditto](5.5-kien-truc-ditto/) | khởi tạo 52 Thing cho topology 22 host | cần Ditto |
| 5.6 Tự động hóa với AWS (ND4) | [5.6-tu-dong-hoa-aws](5.6-tu-dong-hoa-aws/) | ba kịch bản lặp, đối chứng, cân bằng tải | testbed và AWS |
| 5.7 Vòng kín (mở rộng) | [5.7-vong-kin](5.7-vong-kin/) | A/B bảo vệ, phép thử định vị | testbed |
| 6.2.2 Sự cố trên link chỉ có TCP | [6.2.2-co-che-bo-sot-s1-s2](6.2.2-co-che-bo-sot-s1-s2/) | excess trên 5 run giảm băng thông s1-s2, phép thử hàng đợi | offline, testbed |
| Hình và bảng tự sinh | [hinh-va-bang](hinh-va-bang/) | script vẽ hình độ trễ, hình A/B, bảng kiểm mù | offline |

## Giữ bản sao khớp với tệp gốc

Danh sách tệp và tên bản sao của từng thư mục nằm ở `scripts/dong_bo_ket_qua_bao_cao.py`.

```bash
python3 scripts/dong_bo_ket_qua_bao_cao.py --check   # báo bản sao nào thiếu, lệch hoặc thừa
python3 scripts/dong_bo_ket_qua_bao_cao.py           # chép lại từ tệp gốc
```

## Hai lưu ý khi chạy lại

- Đừng gọi trực tiếp các script trong `scripts/` để chạy lại. Một số từ chối ghi đè tệp đã có,
  một số khác (launcher của Mục 5.1, 5.2) ghi đè thẳng `results/report/`. Các script trong thư
  mục này đã lo việc đó.
- Hợp đồng thu dữ liệu ghi tên máy. Các chiến dịch thu của GĐ4 (`gd4`, `gd4r`) chỉ chạy trên
  máy `dt4n-research-01`, máy đã thu toàn bộ dữ liệu. Muốn thu lại trên máy khác, tạo hợp đồng
  mới theo mẫu `ml/gd4rcampaign.py` với tên máy mới, rồi chấm bằng `scripts/gd4_score.py`.

## Tên bản sao và tệp gốc

Danh mục script theo mục báo cáo ở [scripts/README.md](../scripts/README.md).

| Bản sao | Tệp gốc |
|---|---|
| `5.1-phan-chieu-trang-thai/doi-chieu-va-20-lan-tat-link.json` | `results/report/verification.json` |
| `5.1-phan-chieu-trang-thai/do-tre-dong-bo-len.json` | `results/report/latency_up_randomized.json` |
| `5.1-phan-chieu-trang-thai/chay-lien-tuc-30-phut.json` | `results/report/soak_30min.json` |
| `5.2-dieu-khien-tu-xa/do-tre-lenh.json` | `results/report/latency_command_randomized.json` |
| `5.2-dieu-khien-tu-xa/thoi-gian-tung-chang.json` | `results/report/command_flow.json` |
| `5.2-dieu-khien-tu-xa/phan-hoi-ditto-408.json` | `results/report/command_ack_timeout3.json` |
| `5.3-phat-hien-bat-thuong/mo-hinh/envelope-2.1.0.json` | `models/envelope-2.1.0.json` |
| `5.3-phat-hien-bat-thuong/mo-hinh/detector-release-2.1.0.json` | `models/detector-release-2.1.0.json` |
| `5.3-phat-hien-bat-thuong/mo-hinh/bang-bao-toan-residual.json` | `results/report/gd4_conservation.json` |
| `5.3-phat-hien-bat-thuong/mo-hinh/bien-ban-hoc-lai.json` | `results/report/gd4_retrain.json` |
| `5.3-phat-hien-bat-thuong/mo-hinh/ma-bam-du-lieu-huan-luyen.json` | `results/report/gd4_manifest.json` |
| `5.3-phat-hien-bat-thuong/tap-phat-trien/excess-dual-va-iforest.json` | `results/report/gd4_devset.json` |
| `5.3-phat-hien-bat-thuong/tap-nghiem-thu/cau-hinh-25-run.json` | `results/report/gd4r_contract.json` |
| `5.3-phat-hien-bat-thuong/tap-nghiem-thu/ma-bam-du-lieu-nghiem-thu.json` | `results/report/gd4r_manifest.json` |
| `5.3-phat-hien-bat-thuong/tap-nghiem-thu/cham-giam-bang-thong-flood-tai-cao.json` | `results/report/gd4_acceptance_v21.json` |
| `5.3-phat-hien-bat-thuong/tap-nghiem-thu/cham-lai-mot-run-tai-cao.json` | `results/report/gd4_acceptance_v21_rn_retry.json` |
| `5.3-phat-hien-bat-thuong/tap-nghiem-thu/cham-chay-nen-2-gio.json` | `results/report/gd4_acceptance_v21_rs.json` |
| `5.3-phat-hien-bat-thuong/tieu-chi-ghi-truoc/tieu-chi-nghiem-thu.json` | `results/report/gd4_acceptance_prereg.json` |
| `5.3-phat-hien-bat-thuong/tieu-chi-ghi-truoc/tieu-chi-nghiem-thu.md` | `results/gd4/prereg.md` |
| `5.4-what-if/kiem-hoi-cuu.json` | `results/report/gd3_whatif_validation.json` |
| `5.4-what-if/kiem-mu-du-doan.json` | `results/gd3/blind_predictions.json` |
| `5.4-what-if/kiem-mu-ket-qua.json` | `results/gd3/blind_result.json` |
| `5.5-kien-truc-ditto/khoi-tao-thing-22-host.json` | `results/report/bootstrap_scale.json` |
| `5.6-tu-dong-hoa-aws/tung-luot.jsonl` | `results/cloud/gd1_trials.jsonl` |
| `5.6-tu-dong-hoa-aws/tong-hop-theo-kich-ban.json` | `results/cloud/gd1_receipt.json` |
| `5.7-vong-kin/tieu-chi-ghi-truoc.json` | `results/report/gd4cl_prereg.json` |
| `5.7-vong-kin/kiem-offline-luat-chon.json` | `results/report/gd4cl_offline_check.json` |
| `5.7-vong-kin/ab-bao-ve.json` | `results/report/gd4cl_ab.json` |
| `5.7-vong-kin/thu-dinh-vi.json` | `results/report/gd4cl_c1.json` |
| `6.2.2-co-che-bo-sot-s1-s2/excess-5-run-s1-s2.json` | `results/report/gd4_s1s2_excess.json` |
| `6.2.2-co-che-bo-sot-s1-s2/hang-doi-offload-bat-lan-1.json` | `results/probe/degrade_sensor_s1-s2_f0.8275_20260917T045444Z.analysis.json` |
| `6.2.2-co-che-bo-sot-s1-s2/hang-doi-offload-bat-lan-2.json` | `results/probe/degrade_sensor_s1-s2_f0.8275_20260917T045726Z.analysis.json` |
| `6.2.2-co-che-bo-sot-s1-s2/hang-doi-3-dieu-kien.json` | `results/probe/v2_report.json` |
