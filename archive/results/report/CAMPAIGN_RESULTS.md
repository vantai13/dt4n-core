# Lesson 5.4 — Kết quả thu mạng thật

Đã tiếp tục từ `ea43ab7`: kiểm tra phần chuẩn bị có sẵn, bổ sung runner/launcher, chạy smoke fault trước, thu chiến dịch và audit lại trên toàn bộ dữ liệu mới. Hợp đồng Lesson5.3 và split không đổi.

## Kết quả nghiệm thu

| Kiểm tra | Kết quả thực chạy |
|---|---|
| Run | 18/18 đạt, 0 hỏng, complete=True |
| Snapshot | 1080 raw; 1062 sau bỏ warmup 1 tick/run |
| Base rate test | 160/590 = 27.12% |
| Luôn đoán normal | Accuracy tham chiếu 72.88%; chưa phải score của model |
| Lỗi log của run được chấp nhận | 0 ERROR/CRITICAL/Traceback ở toàn bộ 18 log |
| Test | 163 passed, 4 skipped; các skip là test command live riêng |
| Audit | {'BO_QUA': 106, 'LOAI': 65, 'GIU': 34, 'CHAT_VAN': 18} |
| Missing loss raw | 1.7593% |
| Missing loss còn sau warmup | 8 ô; 8 dòng được GIỮ |

## Runner và sửa lỗi

- Launcher .venv kiểm hash ba chiều trước khi dọn Mininet/khởi động Ryu. Runner dùng sudo/Python hệ thống, đọc đúng fault_parameters từ JSON; không nạp NumPy/pandas trong đường thu.
- Sửa health dùng make_thing_id_host theo namespace; không biến Thing vắng mặt thành throughput 0. Bootstrap policy cũng lấy POLICY_ID của namespace `org.dt4n.ml`.
- Sửa thứ tự health: kiểm ngay sau steady-state, trước forced refresh. Refresh ép thêm collect trên cache chung có thể lấy khoảng ngắn giữa các burst TCP; đọc ngay sau đó từng báo khoảng 0.10 dù traffic TCP đã kết nối. Test hồi quy mô phỏng .40 trước refresh/.10 sau refresh. Giữ ngưỡng .30; dữ liệu sau sửa được kiểm chứng bằng chạy live.
- Manifest ghi nguyên tử khi có lỗi và sau từng run. Sidecar ghi trước đổi tên raw; runner từ chối ghi đè raw đã chấp nhận. Resume kiểm checksum, record và design SHA; --only kiểm run ID. Quarantine giữ các lần thử bằng tên attempt riêng.
- Gate runtime_log_ok nhận đúng định dạng [ERROR]/[CRITICAL], có test hồi quy. Audit độc lập đọc lại toàn bộ log sau chiến dịch.

## Các lần thử bị loại

Lượt đầu thu đủ 18 run nhưng 5 run có health ERROR rồi tự hard-reset phục hồi trước thu. Chúng bị loại theo cổng log, không được che bằng đổi mức logging. Dựng mạng trước mỗi run vẫn tái hiện ở 2 lần thu lại; runner dừng đúng sau 2 lỗi liên tiếp. Sau sửa thứ tự health/refresh, thu lại 5 run với hard_every=1; các run còn lại giữ nguyên checksum. Fault, tải, seed, timing và split không đổi.

Dữ liệu lỗi vẫn ở data/phase5/quarantine, sidecar giữ initial_checks hoặc initial.meta.json. Log lỗi có bản review logs/ml_rejected_*.log. campaign_collection_history.json giữ manifest trước sửa và lý do loại; chỉ 18 run đạt cổng cuối được dùng trong audit/base rate.

## Nhãn và grace

`point-wise; label[t]=1 iff inject_tick < t <= revert_tick; grace=2 ticks`

Callback chạy sau snapshot đã flush: tick20 thuộc nền; tick21..40 là fault; tick41 trở lại nhãn0. Hai tick grace21/22 vẫn label1, được loại khỏi cửa sổ signal check và sẽ loại khỏi tính miss/recall theo quy tắc đã chốt khi làm Lesson5.5. Lưu event tick/t_rel, wall t_source, apply_ms và completed_t_rel thật; t_inject/t_revert trong metadata là lịch danh nghĩa. Mỗi rate là phép đo trên một khoảng, không phải giá trị tức thời.

## Tín hiệu từng run

| Run | Split | Snapshot | Max separation |
|---|---|---:|---:|
| F-shift-s1-s2-s3007-r1 | test | 60 | 749.597 |
| F-degrade-s1-s2-s3003-r1 | test | 60 | 11.486 |
| F-degrade-s2-s3-s3004-r1 | test | 60 | 288.827 |
| N-vary-s1007-r1 | train | 60 | — |
| N-load4M-s1005-r1 | train | 60 | — |
| C-vary-s2002-r1 | test | 60 | — |
| F-admin_down-s1-s2-s3001-r1 | test | 60 | 100.0 |
| F-flood-h2_to_srv2-s3006-r1 | test | 60 | 348.672 |
| F-flood-h1_to_srv1-s3005-r1 | test | 60 | 499.847 |
| F-shift-s1-s3-s3008-r1 | test | 60 | 749.276 |
| N-load1M-s1001-r1 | train | 60 | — |
| N-vary-s1008-r2 | train | 60 | — |
| F-admin_down-s1-s3-s3002-r1 | test | 60 | 100.0 |
| N-load4M-s1006-r2 | train | 60 | — |
| N-load1M-s1002-r2 | train | 60 | — |
| N-load2M-s1004-r2 | train | 60 | — |
| N-load2M-s1003-r1 | train | 60 | — |
| C-load2M-s2001-r1 | test | 60 | — |

Separation là kiểm dấu vết trên expected_links, có sàn vật lý; không phải recall hoặc hiệu năng detector. Coverage8/8 ở Lesson5.3 là giả thuyết trước thu, không tự trở thành coverage thực đo8/8.

## Audit và missing trên 18 run

Dùng point-wise labels_from_events và chính sách DT4N-M1, không dùng nhãn fault cho toàn bộ run. Giữ metadata/seed/split/target/time/provenance ngoài model input. Báo cáo pilot không bị ghi đè.

Ngưỡng đơn biến cũ của pilot (≥5 feature GIỮ có auc_dist>0.5) **không đạt**: bộ point-wise này có0feature vượt0.5. Các loại fault có hướng tăng/giảm trái nhau, cùng tải normal biến thiên; audit gộp không tương đương phép so pilot từng profile. Đây là giới hạn cần xử lý ở chiến lược feature/evaluation, không được tuyên bố tất cả gate Lesson5.1 đều xanh. Cổng tín hiệu từng intervention ở Lesson5.4 vẫn đạt; chưa có score detector.

exec_index là chỉ số thứ tự trong hợp đồng; started_utc/events/history lưu thời gian thực, kể cả các lần thu lại sau lỗi.

Cột state_up thay đổi: link-s1-s2.status.state_up, link-s1-s3.status.state_up. Hai link admin-down sống lại; các trạng thái host/switch/link không bị tác động vẫn có thể là hằng số.

Missing ngoài warmup được ghi từng tick/link trong campaign_missing_analysis.json. counter_reset xuất hiện ở tick21/41 của degrade/shift, phù hợp việc cấu hình qdisc lúc inject/revert. Đây là thiếu gắn với can thiệp có sự kiện quan sát được; không suy diễn rằng phép so sánh tỉ lệ chứng minh MNAR tổng quát. Không fillna(0), giữ dòng và missing indicator; lựa chọn feature/train-only xử lý NaN thuộc Lesson5.6.

Tỉ lệ chất lượng sau bỏ warmup:

| Cửa sổ | Cờ | Invalid/total | Tỉ lệ |
|---|---|---:|---:|
| background | qdiscValid | 4/7216 | 0.0554% |
| background | rateValid | 0/11726 | 0.0000% |
| fault | qdiscValid | 4/1280 | 0.3125% |
| fault | rateValid | 0/2080 | 0.0000% |

Background gồm trước inject và sau revert. JSON giữ riêng baseline/fault từ sidecar để không lẫn cửa sổ.

## Provenance và backup raw

Hash hợp đồng: `80b94fb9a53e2341562641cc737cf0dc1a720c203b18d6168a2b58baca1d640c`. Provenance lúc thiết kế giữ nguyên; không dùng hash thiết kế làm hash lúc thu.

Source commit của 18 run: `9075f6e26ee6f105cdbacd57a740e9b2b1028540` (5 run), `6ad5d905f750073820229efbade8b755dab29c90` (12 run), `8ca440556d06740bc53bf0b7f6e6ee384eaac0ee` (1 run). Mọi run source_dirty=false. git_dirty=true được giữ trung thực vì log/sidecar/manifest sinh khi chạy; source_dirty_files loại riêng các đường artifact runtime, không đặt git_dirty=false giả.

Raw chính: `/home/ubuntu/dt4n-core/data/phase5/raw/`; bản collection riêng: `/home/ubuntu/dt4n-core-campaign/data/phase5/raw/`.

Backup đầy đủ accepted/quarantine/meta/history: `/home/ubuntu/dt4n-core-phase5-raw-20260915.tar.gz`.

SHA-256 archive: `6fb6cdaae90b4c81b797a724c2501b4c516c6686293b97afd5b13694b8a29ebf`; đã đọc lại archive và kiểm checksum 18 raw. Raw/archive chỉ nằm trên máy này, chưa upload kho ngoài/GitHub. GitHub chứa code, sidecar, manifest, log review và report; clone GitHub riêng chưa đủ raw để train. Hash không thay thế lưu trữ dữ liệu.

Khôi phục archive vào clone:

```bash
tar -xzf /home/ubuntu/dt4n-core-phase5-raw-20260915.tar.gz -C /path/to/dt4n-core
```

## Lệnh đã chạy / chạy lại

```bash
.venv/bin/python -m pytest -rs --junitxml=results/report/phase54_runner_pytest.xml
.venv/bin/python -m scripts.check_ml_campaign
.venv/bin/python scripts/launch_ml_dataset.py --only F-admin_down-s1-s2-s3001-r1
.venv/bin/python scripts/launch_ml_dataset.py
.venv/bin/python scripts/launch_ml_dataset.py --hard-every 1  # lượt thu lại sau sửa
.venv/bin/python -m scripts.audit_features --campaign
.venv/bin/python -m scripts.analyze_missing --campaign
```

Launcher dùng checkout collection sạch ở /home/ubuntu/dt4n-core-campaign và .venv tuyệt đối của repo chính. Khi chạy lại, phải giữ source sạch; artifacts runtime được ghi đúng dirty state. DT4N_CAMPAIGN_NAMESPACE tùy chỉnh namespace; DT4N_RYU tùy chỉnh binary.

Bằng chứng: [manifest](ml_dataset_manifest.json), [nghiệm thu](campaign_acceptance.json), [audit CSV](campaign_feature_audit.csv), [missing JSON](campaign_missing_analysis.json), [history](campaign_collection_history.json), [backup receipt](campaign_raw_backup.json), [full test](../../logs/phase54_runner_final_pytest.log), [precheck](../../logs/phase54_runner_prechecks.log).

Chưa train hoặc đánh giá detector; bước kế tiếp là Lesson5.5 ground truth.
