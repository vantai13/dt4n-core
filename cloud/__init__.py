"""cloud/ — Phần AWS của DT4N (GĐ1, Nội dung 4 của thuyết minh).

Gồm:
  config.py    — cấu hình chung (region, tên tài nguyên, trần an toàn)
  infra.py     — dựng / xem / thu phóng tay / thử cân bằng tải / dọn hạ tầng
  twin.py      — hình dạng Thing 'org.dt4n:cloud-pool' trong Ditto
  collector.py — đọc AWS định kỳ, đẩy trạng thái nhóm máy lên Ditto
  actuator.py  — hai lệnh chạm AWS: đặt số máy, thay máy hỏng (có audit ghi trước)
  controller.py— đọc twin, quyết định số máy cloud (quá tải / srv1 sập), gọi actuator
  experiment.py— thí nghiệm GĐ1.5: chạy lượt, đo từng chặng, đối chứng, receipt
"""
