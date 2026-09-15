# Lesson 5.4 — Chuẩn bị harness, chưa thu chiến dịch

Phần này thực hiện hai hướng dẫn đính kèm tiếp từ `7aa1c03`. Hướng dẫn thứ hai yêu cầu module campaign, ba patch và ba lệnh kiểm chứng trước khi viết launcher/runner. **Chưa chạy Mininet, chưa sinh 18 run, chưa có sidecar hoặc manifest thu thật.**

## Đã triển khai

- `ml/campaign.py`: hash hợp đồng, kiểm integrity, traffic plan, dựng scenario từ fault_parameters đã khóa, verify một run, signal probe và builder manifest/base rate. Import numpy chỉ nằm trong recompute được launcher .venv gọi; đường kế hoạch/scenario không nạp numpy/pandas.
- Collector thêm run_meta và on_tick. Callback chạy cùng luồng, sau JSONL đã flush; giữ history xuyên suốt. Thời lượng, cadence và t_rel dùng monotonic; t_source wall-clock vẫn giữ cho đối chiếu Ditto. Pretty/JSONL đóng bằng context manager khi callback lỗi. Callback phải tự giữ net_lock khi apply/revert; chưa có runner thực thi hook fault trong bài này.
- Flatten đọc scalar từ khối run, giữ tick/t_rel, từ chối tick nhúng khác chỉ số dòng. Schema bổ sung các field split/fault/target/time/provenance vào metadata để tránh đưa nhãn vào model. Không thay JSONL pilot cũ.
- schedule_with_preroll kiểm schedule/pre-roll nguyên, không âm; chèn mức đầu trong pre-roll và dịch nominal waveform. Traffic dự kiến 5+60+10=75 giây.
- gitignore JSONL và partial ở raw/quarantine; tạo thư mục với .gitkeep. Meta JSON và manifest không bị ignore, sẽ commit sau thu. Hash bảo đảm tính toàn vẹn khi có file, không thay thế lưu trữ/backup raw; raw vẫn cần giữ ở ổ đĩa hoặc kho dữ liệu ngoài Git.

## Ba kiểm chứng đã chạy

```bash
.venv/bin/python -m scripts.check_ml_campaign
.venv/bin/python -m pytest -rs --junitxml=results/report/phase54_prepare_pytest.xml
```

Script check thực hiện cả ba bước được yêu cầu: integrity, 18 traffic plan và timeline pre-roll. Có thêm subprocess `/usr/bin/python3` dựng tất cả plan/scenario, kiểm không có numpy/pandas/matplotlib trong sys.modules.

| Kiểm tra | Kết quả thực chạy |
|---|---|
| stored SHA = hash nội dung JSON = recompute từ design | True |
| SHA hợp đồng | 80b94fb9a53e2341562641cc737cf0dc1a720c203b18d6168a2b58baca1d640c |
| Run trong hợp đồng | 18 |
| Thời lượng iperf dự kiến | 75 s |
| Kết thúc traffic danh nghĩa theo t_rel | +70 s, lớn hơn thời lượng ghi 60 s |
| Python hệ thống dựng plan/scenario | Không nạp numpy/pandas/matplotlib |
| Full pytest | 152 passed, 4 skipped; không failed/error |
| Test campaign riêng | 36 ca đạt |

Bốn skip yêu cầu hệ thống live Ditto/Mininet/Command Agent. Kiểm chứng hook dùng collector giả, test verify dùng snapshot tổng hợp; đây không phải nghiệm thu campaign thật.

[Output ba lệnh gốc](../../logs/phase54_prechecks.log) · [Output check bổ sung](../../logs/phase54_system_prechecks.log) · [JSON kết quả](../../results/report/phase54_prechecks.json) · [Log full test](../../logs/phase54_prepare_pytest.log) · [JUnit](../../results/report/phase54_prepare_pytest.xml)

## Timeline varying danh nghĩa sau prefix

| t_rel bắt đầu | t_rel kết thúc | Mbps/client đầu |
|---:|---:|---:|
| -5 | 0 | 1 |
| 0 | 10 | 1 |
| 10 | 20 | 3 |
| 20 | 30 | 2 |
| 30 | 40 | 5 |
| 40 | 50 | 1 |
| 50 | 70 | 4 |

75 giây tổng bắt đầu ở -5 nên kết thúc ở +70, không phải +75 như một dòng trong ví dụ. Đây là tính schedule, chưa đo iperf thật. Shell khởi động nối tiếp có drift; xoay segment giữa client vẫn làm schedule_nominal chỉ đúng cho client đầu. Runner sau cần ghi thực tế từng client và chọn cách prefix sau rotation nếu muốn pre-roll đồng nhất cho mọi client. Không khẳng định vá prefix đã làm waveform của tất cả client khớp nominal đến mili giây.

## Các sửa chữa so với mã mẫu

1. Integrity so cả nội dung JSON. Nếu chỉ so stored và recomputed, sửa fault_parameters trong JSON nhưng giữ stored SHA sẽ vẫn PASS. Load còn kiểm n_runs/IDs/order/split nhất quán; ma trận đã khóa không bị ghi lại.
2. Missing flag hoặc missing link được tính invalid trên mẫu số đủ tám link; không chỉ đếm các cờ tồn tại để tỷ lệ thiếu nhỏ giả. Baseline phải có đủ link.
3. Probe bỏ NaN/inf và bool ở numeric. Mẫu không hợp lệ không thành zero; separation dùng std nền và floor vật lý, **không phải Cohen’s d pooled/AUC của Lesson 5.1**. Floor 10.000 bytes/s =0,08 Mbps; loss0,1 điểm phần trăm; state0,01. Đây là ngưỡng harness quy ước, cần kiểm chứng sau thu.
4. Callback sau ghi tick20 inject thì tick20 vẫn là nền; fault đo từ tick21. Revert sau ghi tick40 thì tick40 còn fault, tick41 mới trở về nền. Cửa sổ signal/validity/base-rate đã dịch +1 phù hợp; grace thêm hai tick cho probe. Timestamp event thực phải ghi tại apply/revert, không copy t_rel callback làm thời điểm hoàn tất thao tác.
5. Verify kiểm tick nhúng, t_rel hữu hạn/tăng, version/run_id, events đúng hai cái/đúng thứ tự/đúng thời gian và admin_down quan sát được. Baseline invalid bị gate; invalid trong fault chỉ ghi lại, không có quality gate riêng. Tuy vậy signal gate có thể FAIL khi mọi probe biến mất; dữ liệu lỗi cần quarantine và ghi nguyên nhân, không xóa để làm bộ test đẹp hơn.
6. Builder manifest chỉ complete khi đúng toàn bộ run contract, checks passed và integrity match; không coi outcome status=ok với checks fail là thành công. Base rate là đếm tick theo vị trí callback event, chưa phải phép căn thời gian thành phẩm của Lesson5.5.

## Việc còn lại trước thu thật

Theo đoạn cuối hướng dẫn, launcher/runner đầy đủ sẽ được viết tiếp: cleanup `mn -c` trước Ryu, integrity trước startup, thực thi từ JSON chứ không tính severity lại, reset/verify baseline, dừng traffic tự bật của soft_reset, pre-roll, hook event thực, try/finally revert, atomic write, SHA sidecar, resume kiểm checksum, quarantine và dừng sau hai lỗi liên tiếp. Các hằng số/builder đã có không có nghĩa các cơ chế này đã được runner thi hành.

Nguồn thu cần commit SHA và dirty state lúc thu riêng với provenance lúc thiết kế. CSV audit được bạn định dạng sẵn giữ nguyên ở local, không stage vào commit này. Chưa đánh giá missingness dưới fault thật, signal trên routing thực, waveform, FPR/recall/detection delay hoặc tạo tập train/test mới.
