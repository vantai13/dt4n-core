# Envelope: quyết định trước thực nghiệm sklearn trong workspace

Phạm vi lượt này: bổ sung baseline envelope và kiểm tra IF trên dữ liệu tổng hợp. Không fit IF hoặc chọn siêu tham số từ test chiến dịch. Đây là đăng ký trước chạy detector Phase 6, nhưng đã đọc audit/nhãn test ở Phase 5; không phải một đăng ký mù với test.

Giữ IF72feature, split/hợp đồng/y/masks/missing policy. Phân loại constant train theo hậu tố lossPct, qdiscDropDelta, state_up, loss_max, loss_n_above_alert, links_down: giữ cho envelope. Các constant khác vào dead (nghĩa là không dùng trong cấu hình này, không chứng minh vô ích). Feature biến thiên hợp lệ cũng vào envelope. Không thêm nhiễu vào dữ liệu chiến dịch.

Envelope fit finite min/max trên train sau warmup (472 dòng), không dùng test; ngưỡng strict count>K. K=max count trên cùng train nên K=0 theo định nghĩa, không hiệu chỉnh FPR ngoài mẫu. Missing phải giữ unknown/coverage riêng, không biến thành normal. Phase 6 phải quyết định chính sách cho hybrid/unknown trước khi chấm điểm.

Thực nghiệm tổng hợp đăng ký: 464 dòng, 2 biến Gaussian + 1 constant0, seed0, IF200cây/contamination auto/max_samples256. So score tại cùng tọa độ biến thiên với constant=0/1/53/1e6 và đếm split trên constant. Đối chứng dữ liệu tổng hợp khác có std0.001, không thêm nhiễu vào train chiến dịch. Kỳ vọng constant không được split và score bất biến; số cây dùng kênh nhiễu phải đo, không ép200/200.

Giả thuyết Phase 6 (chưa kiểm chứng): H1 envelope có thể tăng phủ loss/state so với IF; chưa chắc precision/FPR tốt hơn. H2 IF có thể phát hiện trước loss-only envelope ở degrade s2–s3, nhưng không suy ra sớm hơn full envelope vì full envelope cũng thấy rates. H3 OR hybrid không giảm số TP trên các tick có phán quyết chung; precision có thể thấp hơn cả hai nếu FP khác nhau. Không kết luận hybrid tốt hơn trước thực nghiệm.

FPR ngoài mức tải: GroupKFold4config, mỗi fold refit toàn bộ preprocessing/envelope/IF trên fold-train. CV toàn normal không đo recall. Ngưỡng score IF dự kiến phân vị1% train; chỉ là mục tiêu in-sample, không bảo đảm FPR ngoài mẫu. Hyperparameter/seed và protocol phải chốt trước runner Phase 6.

Kiểm tra lý thuyết: 1−0.995^240≈69,97% với giả định độc lập (không gần100%). Mỗi đường đi cây sâu8 có tối đa8split, cả cây có nhiều nhánh nên có thể dùng nhiều hơn8feature. 95% là trần riêng của IF khi từ chối toàn bộ dòng72feature thiếu; không phải trần của mọi detector/hybrid.
