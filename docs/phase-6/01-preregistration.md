# Lesson 6.1 — Đăng ký trước Phase 6

ID: DT4N-P6-PREREG-v1. SHA nội dung: **975c63e7ddaf15cd4a0a2248a41544966d8b223c1bc166575be539c800072081**.
Nhánh `phase/6-train-eval`, tag `phase6-prereg`. Dataset DT4N-D1, labels DT4N-L1, design80b94fb9…; SHA split manifest, ground truth, missing report và source dataset ghi trong `bound_to` JSON.

## Kiến thức đã biết và phạm vi

Phase5 đã xem tín hiệu test (separation, witness/onset, counter_reset), đã fit envelope min/max và thống kê trên normal train. Đã chạy IF trên dữ liệu tổng hợp để đo cột hằng số. Chưa fit IF trên train chiến dịch hoặc chấm điểm detector trên test chiến dịch. Vì vậy đây là khóa quyết định **trước đánh giá detector**, không phải thí nghiệm mù hoặc trước mọi dòng sklearn. Không gọi load_split, không tái sinh manifest trong lesson này; facts đọc từ báo cáo đã commit.

Cơ sở: [Nosek et al., PNAS2018](https://pmc.ncbi.nlm.nih.gov/articles/5856500/) phân biệt sinh giả thuyết từ quan sát với kế hoạch phân tích trước kết quả. Bản này khai báo rõ việc đã khám phá test trong Phase5; cần test độc lập mới để xác nhận tổng quát ngoài campaign này.

## Mốc và coverage

| Detector | Unknown | Dương unknown | Âm unknown | Trần recall theo protocol |
|---|---:|---:|---:|---:|
| IF |26|8|18|95%|
| Envelope |8|4|4|97,5%|
| Hybrid OR |8|4|4|97,5%|

590test=160dương+430âm;118âm C và312âm trước/sau lỗi trong F. Always-normal accuracy72,88% là mốc mô tả, accuracy cấm làm chỉ số hiệu năng. Unknown không báo động: dương tính FN; âm tính TN theo vận hành, **không phải phán quyết normal**. Báo coverage và FPR judgeable-only để không che18âm unknown IF /4âm envelope.

## Giả thuyết có điều kiện bác bỏ

### H1

Phát biểu: On the 2 admin_down runs, envelope recall >= IF recall (mean over seeds, primary config).

Cơ chế: state_up/links_down constant on train -> only envelope sees them; link-s1-s2 rates reach 0 in train (min=0) so rate-only view is ambiguous there.

Bác bỏ khi: envelope recall < IF mean recall on admin_down (pooled 40 ticks).

Cấu hình so sánh: primary mask, max_samples256, q0.01; IF mean five seeds unless hypothesis specifies each seed

### H2

Phát biểu: On F-degrade-s2-s3: envelope delay = 1 tick, every primary IF seed delay = 2 ticks, loss-only envelope delay in [9, 11].

Cơ chế: tick 21 unknown for both (counter_reset); tick 22 unknown for IF only (d1 NaN); full envelope contains link-s2-s3.txRate with train band [268256, 271142] B/s; lossPct first crosses at tick 31.

Bác bỏ khi: envelope delay is not 1, any primary IF seed delay is not 2, or loss-only delay is outside [9,11]; censored also refutes.

Cấu hình so sánh: primary mask, max_samples256, q0.01; IF mean five seeds unless hypothesis specifies each seed

### H3

Phát biểu: IF-only positive ticks (caught by IF, missed by envelope) >= 8 (5% of 160) in >= 4 of 5 seeds.

Cơ chế: degrade s1-s2 has no loss witness and wide train rate bands may hide a low-intensity shift; IF has d1.* and multivariate combinations.

Bác bỏ khi: IF-only ticks < 8 in >= 2 seeds.

Cấu hình so sánh: primary mask, max_samples256, q0.01; IF mean five seeds unless hypothesis specifies each seed

### H4

Phát biểu: Among 4 config folds, the held-out vary fold has the highest held-out alarm rate for BOTH envelope (share of rows with k>0) and IF (q=0.01).

Cơ chế: SCHEDULE_A contains 5 Mbps and +/-3..4 Mbps steps; fixed configs stop at 4 Mbps with no steps -> extrapolation. 4M fold is covered by vary -> interpolation.

Bác bỏ khi: another fold has a strictly higher rate for either detector.

Cấu hình so sánh: held-out normal folds; envelope uncalibrated k>0 alarm rate, IF mean five primary-seed alarm rates; vary ties for highest allowed

### H5

Phát biểu: FPR on C-vary > FPR on C-load2M for both detectors.

Cơ chế: SCHEDULE_B has a 1->5 Mbps step (+4) absent from SCHEDULE_A (max +3); C-load2M equals a train config.

Bác bỏ khi: FPR(C-vary) <= FPR(C-load2M) for either detector.

Cấu hình so sánh: operational FPR on all59ticks of each C run; IF mean five primary-seed FPR; judgeable-only FPR reported separately

H2 là dự đoán cụ thể trên1run, không kiểm định thống kê: bất kỳ độ trễ khác dự đoán hoặc censored đều bác bỏ, thay vì chỉ bác bỏ ởdelay≥5như mẫu. K held-out có thể lớn làm detector không báo dù đã có tín hiệu; ràng buộc missing chỉ cho độ trễ tối thiểu, không bảo đảm delay thực1/2. H3 không gọi recall OR cao hơn là giả thuyết vì đó là tính chất tập hợp theo luật OR.

## Bảng dự đoán10run đã khóa

| Run | Envelope | IF | Delay env/IF | Tin cậy |
|---|---|---|---|---|
| C-load2M-s2001-r1 | lower FPR than C-vary, narrow rate bands may still trigger | lower FPR than C-vary; not guaranteed near q | not applicable: normal control | moderate |
| C-vary-s2002-r1 | higher FPR than C-load2M | higher FPR than C-load2M around untrained load steps | not applicable: normal control | moderate |
| F-admin_down-s1-s2-s3001-r1 | recall >= IF expected; calibrated K can suppress small violation counts | rate zero may be familiar in train | 0 expected for envelope; IF may be censored | low: K not yet calibrated |
| F-admin_down-s1-s3-s3002-r1 | relatively high recall expected if K permits state violation counts | relatively high recall from unfamiliar zero rates | 0 / 0 expected | moderate |
| F-degrade-s1-s2-s3003-r1 | low recall expected; wide normal load envelope | low to moderate recall; temporal/multivariate changes may help | censoring possible for both | low |
| F-degrade-s2-s3-s3004-r1 | relatively high recall expected from narrow fixed-background rate band | relatively high recall expected, subject to fitted train threshold | 1 / 2 expected; loss-only 9..11 | low to moderate: structural minima do not guarantee threshold crossing |
| F-flood-h1_to_srv1-s3005-r1 | relatively high recall expected from loss/rate violations | relatively high recall expected from rates | 0 / 0 expected | moderate |
| F-flood-h2_to_srv2-s3006-r1 | relatively high recall expected from loss/rate violations | relatively high recall expected from rates | 0 / 0 expected | moderate |
| F-shift-s1-s2-s3007-r1 | relatively high recall expected | relatively high recall expected | 1 / 2 expected because of missing features | moderate |
| F-shift-s1-s3-s3008-r1 | relatively high recall expected | relatively high recall expected | 1 / 2 expected because of missing features | moderate |

Tin cậy là đánh giá định tính, không xác suất thống kê. Thấp ở các run phụ thuộc K chưa học; không sao chép dự đoán “recall cao chắc chắn” từ separation. Không mở feature test để chỉnh dự đoán trong lượt này.

## Quyết ước đóng

Chính point-wise eval_primary (chỉ warmup); phụ eval_sensitivity2/2. Không PA, không chọn best threshold trên test. Recall+FPR luôn báo cùng nhau; precision mô tả riêng campaign, không suy vận hành. FPR control, trong F, tổng, tổng judgeable-only; phụ dùng giao tick cả hai judgeable. Zero denominator=>None kèm mẫu số. Delay từtick21đếnfirstalarm≤40, không phát hiện=>censoredNone; median trên sự kiện phát hiện kèm số censored, không mean.

IF300cây,max_features1.0,bootstrapFalse,contaminationauto; max_samples256chính và1.0phụ,seed0..4; score_samples thấp là bất thường; alarm strict score<quantile(train_scores,q), linear interpolation, q0.01chính và0.005/0.02/0.05phụ. Báo tất cả cấu hình, không chọn theo test; mean/sample-std/min/max theo5seed.

Envelope chính countstrictviolation>K. **K Phase6 = max held-out k** qua4configfold, khác K=0fit-in-sample Phase5. Mỗi fold refit preprocessing,selection,link_stats,bounds bằng fold-train; chỉ dùng fold-validation đầy đủ feature cho calibration. Không có dòng calibration=>dừng, không fallback. Final bounds refit472normal, K học ghi model artifact mới; không ghi đè manifest Phase5.

Phụexcess=sum khoảng vượt biên/max(width,floor) mỗi cột; E=max held-out excess. Floor rx/tx10000B/s,loss0.1%,state0.01,cột khác1.0đơn vị tương ứng. Loss-only ablation chỉ8rawlossPct, tự refit/calibrate riêng; không gọi35cột riêng là “loss-only”.

Hybrid OR báo nếu ít nhất1member judgeable báo; unknown chỉ khi cả2unknown. Bootstrap2000cluster theo run_id phân tầng2C/8F,seed20260916,CIpercentile2.5/97.5; không refitdetector, tính mỗi seed riêng, không coi5seedlà5campaignđộc lập. Không CI theo loại fault chỉ2run; báo từng run. Tỷ lệ undefinedbootstrap loại khỏi quantile và báo sốreplicatehợp lệ.

Noisecontrol: Gaussiantrain464x72 vàtest590x72, RNG10000+seedvẽtrainrồitest; IFprimaryconfig, dùng unknownmask IF giốngcampaign để so coverage; chỉ là controltổng hợp.

## Đối chiếu hướng dẫn và giới hạn

Manifest overlap36; fullenvelopecórate, không rờiIF và không chỉloss. Dải train txRates2–s3 thật268255.64–271141.9B/s; onsetraw0chưa làdelaydetector. Tách2degradekhácnhau. PHASE_6.md được nhắc trong attachment nhưng không có trong repo hiện tại, nên không khẳng định đã sửa file đó.

Quantile0.1% không dùng theo protocol; quantile nội suy vẫn tính được trên464điểm, nhưng tail dưới1mẫu có chứng cứ yếu, không gọi là “bất khả tính”. FPR calibration không bảo đảm FPR ngoài mẫu; bootstrap chỉ10run nhỏ có hạn chế. Hypothesis được ủng hộ không chứng minh cơ chế nhân quả hay tổng quát mạng thật.

## Bất biến, lịch sử và amendment

Script từ chối ghi đè (kể cả race bằng open x). Hash canonical JSON phủ content; timestamp/git đầu ghi nằm ngoài content. Hash kiểm tra nội dung với giá trị đã neo, không tự chứng minh thời điểm hay tác giả chưa chạy privateexperiment. Git test dùng ancestororder thaytimestamp, tag/remote cung cấp mốc lịch sử để xem; không coi push là bằng chứng chắc chắn chưa thử riêng.

Sau commit, không sửa phase6_prereg.json hoặc script sinh nội dung; không tái sinh splitmanifest/groundtruth bị ghim SHA. Thay đổi cần phase6_prereg_amendment_<n>.json ghi lý do, ngày, SHA gốc và đã/chưa nhìn kết quả test. Báo mọi deviation và tách exploratory. Nếu lỡ detectorcode trước đăng ký, khai báo lịch sử; không đổi timestamp để che.

## Kiểm chứng và file

```bash
.venv/bin/python -m pytest test/test_phase6_prereg.py -ra
.venv/bin/python -m pytest test -ra --junitxml=results/report/phase61_pytest.xml
```

JSON:results/report/phase6_prereg.json; log sinh:logs/phase61_build_prereg.log; log từ chối ghi đè:logs/phase61_overwrite_refusal.log. Trước commit9passed/1skiptestlịch sử; saucommit phải10passed. Không tạo ml/detectors trong6.1. Dừng ởđăng ký trước đểreview trướcLesson6.2.
