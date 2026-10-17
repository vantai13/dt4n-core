# Phase 0 — Notes (lệnh đã chạy, lỗi gặp + cách fix)


## Nghiệm thu bản Core 2026-09-15

Xem `results/report/ACCEPTANCE.md` và các log tương ứng. Bản Core kiểm chứng bằng Mininet thật, Ditto thật và namespace `org.dt4n.core`; import/test được đặt PYTHONPATH trỏ kho mới. Kết quả của phase này được tổng hợp khi suite hoàn tất, không dùng số kỳ vọng làm số đo.


### Kết quả chạy thực tế bản Core

Đã tách kho từ d45cf4f; import 0/22 lỗi, các module đều từ dt4n-core. Pytest 23 passed, 4 skipped, 0 failed. Xem results/report/pytest.xml. Hai test bổ sung bảo vệ việc phân trang Ditto và cursor lặp.

## Kiểm chứng trước ML — v2

Code v2: 29 passed, 4 skipped, không warning; bản xuất sạch từ Git cũng qua 29 test. Compose config và nginx -t hợp lệ. Bỏ Swagger/OpenAPI khỏi Git hiện tại; 74 asset static còn giữ khớp source Ditto 3.9.1, kèm license/notice. Xem results/report/ml_clean_export_validation.json và ditto_asset_provenance.json.
