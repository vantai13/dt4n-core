# Dataset card — DT4N-D1 (Lesson 5.6)

## Phạm vi và nguồn

18 run Mininet đã thu ở Lesson 5.4, 1.080 snapshot, collector `v3-qdisc-ratevalid`. Hợp đồng ký SHA `80b94fb9a53e2341562641cc737cf0dc1a720c203b18d6168a2b58baca1d640c` giữ nguyên. Sidecar events tạo nhãn qua ml.labels, không đọc ground_truth.json để tạo dataset. Raw SHA, metadata SHA, events SHA và source SHA ghi trong `ml_dataset_split_manifest.json`. Raw không ở GitHub; cần khôi phục archive theo `campaign_raw_backup.json`.

Không thu lại, không huấn luyện detector. Audit có nhãn test là phân tích mô tả in-sample, không cung cấp feature mô hình.

## API và bốn tầng kiểm tra

```python
from ml.dataset import load_split
s = load_split()
# Fit bằng s.X_train; đánh giá bằng s.X_test và s.y_test.
# Group CV train bằng s.groups_train_config.
```

1. Split theo hợp đồng: 8 train N, 10 test (2 C + 8 F), không giao run_id. Kiểm tra hợp đồng, checksum raw, sidecar/manifest nghiệm thu, record/constants/version, identity và event clock.
2. Delta trong từng run; rolling chỉ quá khứ, groupby + shift(1), mặc định tắt. Tick hiện tại được phép vào raw/delta cho phát hiện tại tick đó; dùng hiện tại không tự động là leakage. Shift là quy ước cửa sổ lịch sử cho rolling.
3. Thống kê rate mean/std fit train, tái dùng cho test. Ghi đầy đủ link_stats cho inference.
4. Chọn feature bằng loại cột, pct_null tối đa20% và nunique trên train; không AUC/nhãn test. Label/mask/config_id/warmup/max_separation bị loại.

API và test chặn lỗi thường gặp, không phải sandbox ngăn người viết code gọi sai. Chữ ký chỉ nhận train_df không chứng minh người gọi không truyền test. `Split.meta` có số đếm test phục vụ báo cáo: code fit/đặt ngưỡng phải chỉ dùng train, không đặt contamination bằng base rate test.

## Kích thước thực đo

| Mục | Giá trị |
|---|---:|
| Train sau warmup | 472 |
| Train bỏ vì NaN feature | 8 (delta priming) |
| Train cuối | **464** |
| Test cuối | **590**, giữ mọi tick sau warmup |
| Feature | **72** = 36 gốc + 36 delta |
| Base rate chính | **160/590 = 0.2712** |
| Base rate độ nhạy | **144/558 = 0.2581** |
| Always-normal accuracy chính | 0.7288 |
| Group train run_id / config_id | 8 / **4** |

36 feature gốc: 10 rate host + 16 rate link + 8 qdiscSentDelta + 2 aggregate rate. Hai aggregate được giữ là `agg.rate_absz_max`, `agg.rate_absz_n_above_3`; chúng dùng link rate, không trộn host rate vào tổng hợp link.

Aggregate loss/state được tạo nhưng **hằng số trên train** nên bị loại bằng luật đã chốt. Điều này không có nghĩa các cột đó vô ích: IF học từ normal không chia được cột hằng số; baseline luật link-down/loss phải được đánh giá riêng ở Phase 6. Không khẳng định IF sẽ thắng luật hay AUC thấp buộc dùng IF trước khi chạy.

## Sửa phép đo onset (5.5b)

Cả 8 F có kênh chẩn đoán vượt z=5 từ tick21: onset sớm nhất **0**. Degrade s2–s3: earliest `link-s2-s3.txRate` onset0; strongest `link-s2-s3.lossPct` onset10. Hai số đo hai câu hỏi khác nhau. Chốt onset2/recovery2, không sửa y/primary. Giữ cả `ground_truth_initial_grace2.json` và `ground_truth_witness_grace10.json` để đối chiếu lịch sử; bản hiện tại `ground_truth.json` có per_channel.

Min first-crossing trên nhiều kênh chỉ là dấu hiệu chẩn đoán, có thể nhạy với nhiễu/multiple comparisons; không chứng minh độ trễ vật lý tối thiểu hoặc detector đa biến chắc chắn bắt được. Recovery vẫn đo lần dưới ngưỡng đầu tiên của strongest witness; không bảo đảm mọi kênh đã phục hồi bền vững.

## Missingness và tick không phán quyết được

Raw sau warmup có 8 ô loss thiếu do counter_reset, nhưng **feature matrix** có 26 tick chứa NaN: **8 fault + 18 normal**. Không dùng số ô loss thô thay số tick missing của X.

- 10 tick1: delta priming sau khi loại warmup (8 F + 2 C), tất cả normal.
- 8 tick21/41: qdiscSentDelta thiếu trên 4 run degrade/shift (4 fault, 4 normal).
- 8 tick22/42: delta qdiscSentDelta kế thừa thiếu từ tick trước (4 fault, 4 normal).

Đây là lý do kỳ vọng ≤4 tick fault thiếu trong hướng dẫn không đạt. Giữ nguyên feature/delta đã chốt; không zero-fill hoặc bỏ test để ép số đẹp. Danh sách từng tick và cột thiếu nằm ở `unjudgeable_rows` trong manifest.

Phase 6 phải trả unknown khi feature cần thiết thiếu; y=1 unknown tính bỏ sót/FN và đếm riêng. Với chính sách từ chối toàn bộ dòng này, recall tối đa **152/160 = 95%**, không phải97,5%; đây là trần tính toán, chưa phải recall detector đã đo. Unknown y=0 cần báo coverage riêng, không tự coi là phán quyết normal. Dòng test và mẫu số primary luôn giữ nguyên.

Rolling ablation có priming lớn hơn và có thể lan missing dài hơn; tạo manifest tên riêng khi ablation, không ghi đè manifest mặc định.

## Cross-validation và inference

4 cấu hình normal: 1M, 2M, 4M, vary; mỗi cấu hình2 run. GroupKFold(config_id)4 fold tương đương leave-one-config-out. **Mỗi fold phải chọn feature và fit link_stats trên fold-train**, rồi transform fold-validation; không chia s.X_train đã preprocess bằng cả8run để báo CV không leakage. load_split hiện chuẩn bị train/test cuối, chưa triển khai fit theo fold. Điều đó thuộc Phase 6.

Inference phải giữ thứ tự72 cột, link_stats train, valid/missing policy, previous-tick state theo run và convention. Hai lần load_split được so sánh DataFrame/Series trực tiếp; không chỉ so base rate.

## Giới hạn nghiên cứu

18 run nhỏ, môi trường giả lập, fault bằng can thiệp, bình thường có4 cấu hình tải. Base rate do thiết kế; không đại diện mạng thực. Nhãn can thiệp không đồng nghĩa mọi feature đều có dấu hiệu từ tick đầu.

AUC≈0.625 chỉ là ví dụ giả định: 25% điểm lỗi tách hoàn hảo, 75% điểm lỗi phân phối giống normal => AUC=0.25×1+0.75×0.5. Không phải trần chứng minh cho dữ liệu thực hay mọi feature. IF không học từ8run fault; 8run fault chỉ dùng đánh giá. Aggregate giúp biểu diễn vị trí lỗi, chưa có bằng chứng cải thiện detector.

Cơ sở kiểm soát leakage: [scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html). [GroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html) bảo đảm group không giao giữa fold. [IsolationForest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html) là mô hình sẽ thử ở Phase 6, chưa chạy trong lesson này.

## Chạy lại và artifact

```bash
.venv/bin/python -m scripts.verify_labels
.venv/bin/python -m scripts.plot_labels
.venv/bin/python -m scripts.build_dataset_manifest
.venv/bin/python -m pytest test -ra --junitxml=results/report/phase56_pytest.xml
```

Manifest: `results/report/ml_dataset_split_manifest.json`; log: `logs/phase56_manifest.log`, `logs/phase56_pytest.log`; màn hình: `results/report/phase56_results_screen.png`. Thiếu raw thì test live skip rõ lý do; lần chạy tại đây có raw và các test dataset live đã chạy.

Validation cuối: **214 passed, 4 skipped**; 24 test dataset (gồm live) đều chạy đạt. Kiểm tra checksum giữ nguyên raw/sidecar/hợp đồng/manifest thu và bằng chứng grace2 ban đầu.

## Cập nhật cuối Phase 5 — envelope (Lesson 5.6b)

Phân loại constant đã thay đổi: `feature_selection_dropped` chỉ gồm cột không hợp lệ theo cấu trúc/null; `dead_features` chứa constant ngoài họ đăng ký; `envelope` chứa cột biến thiên hợp lệ và constant chỉ báo sự cố. Không dùng test để quyết định họ hoặc bounds. “Dead” nghĩa là không dùng ở cấu hình này, không phải chứng minh vô ích về vật lý.

| Mục thực đo | Giá trị |
|---|---:|
| Feature IF | 72, giữ nguyên |
| Feature envelope | **71** |
| Chỉ envelope (constant chỉ báo) | **35** |
| Giao envelope / IF | **36** cột gốc biến thiên |
| Constant khác (`dead_features`) | **33** |
| Envelope fit train | **472** dòng sau warmup |
| Envelope K / k_train_mean | **0 / 0.0** |
| Dòng test envelope / chứa missing | **590 / 8** |

35 cột riêng gồm lossPct8 + qdiscDropDelta8 + state_up16 (8link,5host,3switch) + aggregate3 (loss_max, loss_n_above_alert, links_down). Số68 trong tài liệu gộp **tất cả constant**, không phải68chỉ báo riêng. Không ép số từ dự đoán.

`Split` trả thêm `envelope`, `envelope_threshold`, `X_train_envelope` và `X_test_envelope`. X_train_envelope có472dòng fit envelope, khác X_train IF464dòng vì envelope không cần delta priming. X_test_envelope có cùng index với y_test590dòng. Bounds, số mẫu đo, thứ tự71cột và K đều ghi manifest. `envelope_exceedance_counts` trả k và n_missing riêng; n_missing>0 không được coi là normal chỉ vì k=0. Phase 6 cần chốt alarm/unknown/hybrid protocol trước chấm điểm.

### Vùng mù IF được kiểm chứng

Đã chạy dữ liệu tổng hợp (không dữ liệu chiến dịch), sklearn1.8.0,464dòng,2Gaussian +constant0,200cây,seed0. Constant:0/200cây split, score **−0.3957514693481897** giống hệt ở0/1/53/1e6. Đối chứng tổng hợp std0.001:200/200cây split, score từ−0.385347 khi0 xuống−0.560529 khi1/53/1e6. Không thêm nhiễu vào raw/train chiến dịch. Số200/200 ở đối chứng là kết quả cấu hình này, không định lý cho mọi seed/kích cỡ/nhiễu.

Source và kết quả: `scripts/check_if_constant_blindness.py`, `results/report/if_constant_blindness.json`, `logs/phase56b_if_constant_blindness.log`. Cơ chế split trong [tài liệu IsolationForest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html) giải thích cột hằng số không có ngưỡng chia.

Không dùng IF để kết luận mô hình trực tiếp đọc loss/state đã loại khỏi X; IF vẫn có thể phát hiện sự kiện loss/down **qua rate biến thiên**. Full envelope cũng đọc rate, nên hai tập kênh **có giao**, không thể suy IF sớm hơn full envelope từ loss-only onset10. Khả năng bổ sung và chất lượng hybrid là giả thuyết, chưa kết quả đo.

### K=0 chưa là hiệu chỉnh FPR

Bounds là min/max của chính472dòng train; mọi giá trị finite train nằm trong bounds nên k_train=0 và K=0 theo định nghĩa. Quy tắc count>K hiện tương đương **any violation** ở dòng đầy đủ dữ liệu; chưa cải thiện rủi ro multiple comparisons. Không khẳng định FPR test≈0, envelope tốt hơn luật1% hoặc tốt hơn IF từ ba số in-sample này. Muốn hiệu chỉnh ngoài mẫu phải có calibration split/fold-train riêng trong Phase 6, không đổi K theo nhãn test.

Ví dụ độc lập:1−0.995^240≈69,97%, không gần100%. Cột thực có tương quan và xác suất vượt biên chưa đo, nên ví dụ này không dự báo FPR thực. FPR train0 không chứng minh FPR trên tải mới0.

Trần95% trước đây chỉ áp dụng **IF với chính sách unknown khi bất kỳ72feature thiếu**. Envelope590dòng có8dòng missing (4fault/4normal); nếu từ chối bất kỳ71feature thiếu thì trần riêng97,5%. Hybrid có thể phát cảnh báo từ detector còn đo được; không kết luận “mọi detector không thể vượt95%”. Không tính recall thật trong lượt này.

Đăng ký quyết định/giả thuyết trước thí nghiệm sklearn: `docs/phase-5/07-envelope-registration.md`. Đã xem audit/test ở Phase5 nên không gọi là đăng ký mù. H3 OR có thể có precision thấp hơn cả hai; không giả định precision nằm giữa. Đường đi sâu8 có tối đa8split, cả cây nhiều nhánh có thể dùng hơn8feature.

Chạy lại bổ sung:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m scripts.check_if_constant_blindness
.venv/bin/python -m scripts.build_dataset_manifest
.venv/bin/python -m pytest test -ra --junitxml=results/report/phase56b_pytest.xml
.venv/bin/python -m scripts.build_dataset_report
```

Kết quả màn hình: `results/report/phase56b_results_screen.png`. Manifest trước patch giữ tại `results/report/ml_dataset_split_manifest_pre_envelope.json`; các báo cáo nghiệm thu/ảnh cũ giữ nguyên để truy lịch sử. Không thu lại Mininet, không fit detector trên train chiến dịch hoặc chấm điểm test chiến dịch.

Validation cuối envelope: **220 passed, 4 skipped**; sáu test mới gồm kiểm chứng sklearn, missing/bounds và tái lập envelope trên raw thật đều đạt.
