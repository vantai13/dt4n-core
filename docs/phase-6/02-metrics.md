# Lesson 6.2 — Chỉ số là code

Nguồn duy nhất là `ml.metrics`. Detector phải tạo `EvalFrame` qua `build_frame` bằng tham số keyword-only. Cổng từ chối độ dài khác nhau, nhị phân/khóa/tick sai, khóa trùng, metadata run không nhất quán và alarm tại tick unknown. Không ép alarm về0 để che lỗi. Frame không thể dựng trực tiếp và trả bản sao rows, tránh sửa state sau kiểm tra.

## Ba trạng thái và counts

| Đầu ra | y=1 | y=0 |
|---|---|---|
| alarm | TP | FP |
| normal | FN | TN |
| unknown | FN | TN vận hành |

Unknown âm chỉ có nghĩa không báo oan, không phải phán quyết normal. Vì vậy luôn báo coverage, số unknown và FPR judgeable-only. IF có26unknown (8dương,18âm), envelope có8 (4/4). Detector luôn alarm ở mọi tick judgeable có recall95%/97,5%, FPR vận hành412/430 và426/430, còn FPR judgeable-only=1. Undefined trả `None` kèm mẫu số; không thay bằng0. Accuracy và point-adjust không có API. [Kim et al., AAAI2022](https://ojs.aaai.org/index.php/AAAI/article/view/20680) cho thấy point-adjust có thể làm đánh giá time-series anomaly detection phồng mạnh.

Công thức point-wise micro: recall=TP/(TP+FN), FPR=FP/(FP+TN), precision=TP/(TP+FP), F1=2TP/(2TP+FP+FN). `fpr_breakdown` trả control118âm, trong run F312âm, tổng430âm và từng control run. `scores_by_fault` chỉ báo pooled và từng run; không CI theo fault vì mỗi loại chỉ2run.

## Delay và censoring

Delay là tick alarm đầu tiên trong cửa sổ y=1 trừ tick21, chỉ trên eval_primary. Không phát hiện trả `None` và tăng `n_censored`; báo median của ca phát hiện cùng số censored, không mean. Với alarm hoàn hảo trên mọi tick judgeable của degrade s2–s3, minimum do cấu trúc là IF2tick và envelope1tick. `eval_sensitivity` bị từ chối vì loại transition làm đổi mốc.

## Bootstrap cụm phân tầng

Lấy lại có thay thế nguyên2run C và8run F riêng biệt, giữ mọi tick; cộng counts của run được chọn rồi tính lại tỷ lệ. 2000lần, seed20260916, percentile2,5/97,5 theo prereg. Undefined replicate bị loại và báo `n_valid`; không còn replicate hợp lệ=>CI None. Không refit detector trong bootstrap. Với chỉ8F và2C, CI là xấp xỉ thô; riêng control chỉ có ba tổ hợp bootstrap về danh tính run, nên luôn báo FPR từng run và không diễn giải CI như bằng chứng mạnh.

Test giả bắt trọn4/8F cho thấy cluster CI rộng hơn row-bootstrap ít nhất3lần; test ghim quan hệ và tính tất định thay vì số thập phân phụ thuộc phiên bản. Micro gộp counts; macro không phải chỉ số chính. `summarize_seeds` báo mean, sample std(ddof=1), min/max và từ chối infinity.

## Amendment trước khi đo

[Amendment1](../../results/report/phase6_prereg_amendment_1.json) được commit trước module này và trước CV/testscore. Envelope chính giữ một K. Phân tích phụ chia35indicator và36rate/shared, học K_ind/K_rate riêng trong4fold train, alarm strict OR; equality không alarm. Cả71cột phải finite, nếu không unknown. Nó không thay H1–H5 và không được thay primary sau khi xem test.

Rủi ro đã đăng ký: K chung có thể bị rate ở held-out vary đẩy cao, che state_up/links_down ít vi phạm trên admin-down. Loss-only onset9–11 cũng có thể bị bác nếu loss nhỏ vượt0 trước ngưỡng chẩn đoán z5. Đây là dự đoán falsifiable, không sửa sau kết quả.

## Khác biệt cần nhớ

- Không báo “always alarm FPR=1” ở mẫu số430 khi có unknown; chỉ judgeable-only bằng1.
- Cổng từ chối alarm unknown, không sửa âm thầm.
- Bootstrap theo run, phân tầng; row bootstrap chỉ tồn tại trong test minh họa cách sai.
- FPR primary tính TN vận hành; comparison phụ dùng cùng common-judgeable rows.
- Frozen dataclass một mình không đóng băng DataFrame; implementation dùng constructor token và defensive copy.

## Kiểm chứng

```bash
.venv/bin/python -W error -m pytest test/test_ml_metrics.py -q
.venv/bin/python -m pytest test -ra --junitxml=results/report/phase62_pytest.xml
```

Test dùng skeleton590dòng từ cấu trúc prereg, không dùng feature value hay detector score campaign. Lesson này chưa tạo `ml/detectors`, chưa chạy CV và chưa chấm test campaign.

Validation: **30/30 test metrics đạt với warnings-as-errors; toàn bộ 264 passed, 4 skipped**. Receipt: `results/report/phase62_validation.json`; log: `logs/phase62_pytest.log`. Prereg và amendment tái lập đúng hash; `ml/detectors` vẫn chưa tồn tại.
