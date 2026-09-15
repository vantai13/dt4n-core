# Nguồn gốc mã nguồn

- Kho gốc: https://github.com/vantai13/dt4n
- Commit: d45cf4ff26d8c6204a181f0fa77887e087a4d381
- Ngày tách (UTC): 2026-09-15T08:12:06.938068+00:00
- Trạng thái nguồn: sạch khi copy.

Kho mới giữ phần lõi bốn lớp của đề tài. Lịch sử phát triển vẫn ở kho gốc. Các sửa đổi để kiểm chứng được ghi trong báo cáo nghiệm thu.

## Điều chỉnh sau khi tách để kiểm chứng trên môi trường thật

- `bridge/verify.py`: dùng page size 200 và theo cursor; Ditto đang chạy từ chối size 500 bằng HTTP 400.
- `measurements/measure_command_flow.py`: timeout biên nhận mặc định 0, giống dashboard; tránh cộng 3 giây chờ ack vào phép đo phản ánh trạng thái.
- `measurements/measure_latency.py`, `measure_command_latency.py`: thêm mẫu gốc và số timeout vào dữ liệu trả về cho các lần chạy lại. Đợt nghiệm thu đầu lưu thống kê toàn độ chính xác và từng mẫu làm tròn trong log.
- `test/test_command_security.py`: gửi clientCorrelationId trong payload (SSE không trả header này trên stack hiện tại), timeout 0 và dùng namespace môi trường; giữ nguyên các assert về whitelist/payload/target/idempotency.
- `test/test_phase2_5.py`: thêm hai test hồi quy cho phân trang >200 Thing và cursor lặp.
- Thêm cấu hình Ditto cùng các file nginx phụ thuộc, script nghiệm thu, README và bằng chứng kết quả.

Mọi lần chạy thử chưa đạt được giữ log hoặc JSON với tiền tố `first_`/`ack3_`; báo cáo cuối phân biệt các lần chạy đó với phép đo hoàn tất.

Cấu hình Compose đã đổi đường dẫn bind mount tài liệu sang ditto/static trong kho, bổ sung các tài nguyên phụ thuộc, mặc định Ditto 3.9.1 và thêm override digest của tám image chạy thật. Không thay đổi stack đang chạy.

## Kiểm chứng dữ liệu trước ML — v2 (2026-09-15)

Sửa qdisc counters/validity, profile đa client, injection mnexec, jitter settle và xác nhận reset latency; giữ dataset và thống kê v1. Thêm pilot mạng thật, HTTP timeout=3 probe, test hồi quy, tổng kết và ảnh v2. Bỏ optional Swagger/OpenAPI khỏi cây Git hiện tại; service docs cũng được bỏ khỏi Compose. 74 static asset còn giữ khớp byte với source release Eclipse Ditto 3.9.1, SHA-256 trong ditto_asset_provenance.json; license/notice upstream được bảo tồn trong ditto/upstream.

Không viết lại commit 8660edf; tài liệu upstream của bản v1 vẫn có trong lịch sử. Pilot v2 chưa phải nghiệm thu hiệu quả mô hình ML.

## Lesson 5.1 — Feature audit

Từ commit 9192649, triển khai hướng dẫn đính kèm về schema/flatten/audit và plot, bổ sung map TriangleTopo. Sửa gate chỉ đếm feature được giữ, bỏ cycle_scan_ms khỏi ứng viên, bảo toàn null/unknown state và kiểm tra nhãn. Dùng pooled sample std và AUC có nửa điểm khi hòa; không sao chép các kết luận tổng quát về missingness hoặc hiệu năng mô hình từ hướng dẫn. SHA-256 raw v2 bảo tồn trong feature_audit_summary.json; báo cáo thực tế tại docs/phase-5/01-feature-audit.md.

## Lesson5.2 — Dữ liệu thiếu

Từ f4b8a19, thêm module missing, validity rate collector, timestamp Thing metadata, phân tích/biểu đồ và test. Giữ numeric rate theo hợp đồng cũ, mask invalid ở ML. Sửa gate yêu cầu mọi ô thiếu được giải thích, kiểm toán rate theo run thay vì profile, đếm feature vắng hoàn toàn là không đủ điều kiện train. Wilson/Fisher theo ô không được diễn giải như các mẫu độc lập của pilot. JSONL nguồn giữ nguyên SHA-256.

## Lesson5.3 — Thiết kế trước thu

Từ5518cca, thêm design/matrix, metadata/provenance, faultfactory seeded đúngtarget, LinkAdminDown và varyingtraffic processgroup. Gate kiểmcoverage vàschedule đầyđủ, Git lỗi không giảclean. Điều chỉnh2seedtrainvary cùnglịchA, lịchBtest;severitydegrade dưới nền để giảthuyết cópressure. ContractSHA vàrouting/topologySHA trongJSON; design-time dirty là workingtree lúc sinhartifact, không phải provenance collection. CSV người dùng định dạng có sẵn giữ nguyên và không đưa vào commit này.

## Lesson5.4 — Harness chuẩn bị

Từ7aa1c03, triển khai campaign vàpatch từ hướng dẫn:hash3phía,scenario đọcparams JSON,verification/builder,metadata hookmono vàprefixpre-roll. Bổ sungschema chốngleak label,missingflag tínhinvalid,finiteprobe vàcửasổsaucallback+1. ContractJSON/SHA không đổi;rawJSONL ignored nhưng sidecar/manifest chưa sinh bởi campaign thật. GiữCSV người dùng cósẵn ởlocal.

## Lesson5.4 — Thu mạng thật

Hợp đồng SHA vẫn 80b94fb9a53e2341562641cc737cf0dc1a720c203b18d6168a2b58baca1d640c. Source của run accepted: 9075f6e26ee6f105cdbacd57a740e9b2b1028540 (5), 6ad5d905f750073820229efbade8b755dab29c90 (12), 8ca440556d06740bc53bf0b7f6e6ee384eaac0ee (1). source_dirty=false; git_dirty runtime được giữ nguyên. Thiết kế và thu có provenance riêng.

Giữ18rawaccepted và7rawrejected tại máy, có archive checksum đã kiểm18/18; receipt results/report/campaign_raw_backup.json. Github không chứa raw. Run bị loại và manifest trước sửa trong results/report/campaign_collection_history.json; không thay seed/fault/split sau xem dữ liệu.
