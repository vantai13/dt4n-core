# 5.7 Vòng kín trên testbed (mở rộng)

Vòng kín: detector báo nghẽn, controller chọn một máy khách và giới hạn băng thông của máy đó
qua lệnh gửi tới twin, rồi gỡ thử giới hạn theo lịch. Controller chọn ứng viên theo chiều: chỉ
giữ máy khách có tốc độ gửi trên twin vượt biên trên của chính nó trong mô hình envelope
(`scripts/gd4cl_common.py`), và chỉ hành động khi còn đúng một ứng viên. Detector là bản 2.1.0
của Mục 5.3.

Hai phép đo:

- A/B bảo vệ: h1 flood UDP 47 Mbps tới srv1 trong 120 s; so tốc độ gửi trung bình của h3 khi
  bật và khi tắt controller; 8 khối, mỗi khối 4 lượt theo thứ tự ABBA hoặc BAAB; h2 là đối chứng.
- Phép thử định vị: 4 kịch bản (h3 flood srv1, h2 flood srv2, h1 flood srv2, dừng flood khi
  controller đang gỡ thử), 5 lượt mỗi kịch bản; mỗi lượt được xếp vào chọn đúng thủ phạm, sai
  mục tiêu, hoặc không hành động. Trước mỗi lượt, tải nền được khởi động lại và lượt chỉ bắt
  đầu khi đủ ba luồng TCP và luồng UDP srv1 tới srv2.

## Tệp kết quả

| Tệp | Dùng ở báo cáo |
|---|---|
| `gd4cl_prereg.json` | thiết kế, ngưỡng và cách chấm, ghi trước khi chạy |
| `gd4cl_offline_check.json` | luật chọn ứng viên chạy offline trên 30 run đã có |
| `gd4cl_ab.json` | A/B 32 lượt: h3 gửi 2,146 Mbps khi bật controller, 0,295 Mbps khi tắt; bật cao hơn ở 8/8 khối, p = 0,008; h2 chênh -0,0003 Mbps; 0 lượt hủy; Hình 5.2 |
| `gd4cl_c1.json` | phép thử định vị: 20/20 lượt chọn đúng thủ phạm (5/5 mỗi kịch bản), 0 sai mục tiêu, 0 lượt hủy, 10 lượt thủ phạm khác h1; Bảng 5.9 |

## Chạy lại

### Kiểm offline luật chọn ứng viên

```bash
PYTHONPATH="$PWD" .venv/bin/python scripts/tai_lap_bao_cao.py --muc 5.7   # so khớp, không ghi
PYTHONPATH="$PWD" .venv/bin/python -m pytest -q test/test_gd4cl.py
```

### Thí nghiệm trên testbed (một lệnh)

```bash
scripts/chay_vong_kin.sh        # A/B rồi phép thử định vị; hoặc "scripts/chay_vong_kin.sh ab" / "... c1"
```

Script kiểm môi trường (`scripts/kiem_tra_moi_truong.py --testbed`), dọn Mininet, bật Ryu
riêng từ gốc repo cho từng runner rồi tắt khi xong, và ghi receipt vào
`logs/chay_lai_vong_kin/<thời điểm>/` để không đụng `results/report/`. A/B mất khoảng 1 giờ
30 phút, phép thử định vị khoảng 40 phút. Cần Ditto đang chạy với MongoDB trần ít nhất 1 GiB,
sudo không hỏi mật khẩu, và không có Mininet hay Ryu nào khác đang chạy.

Chạy từng runner bằng tay (bật Ryu trước mỗi runner, vì bước dọn Mininet ở cuối runner dừng
luôn Ryu):

```bash
sudo mn -c && rm -f ditto/port_map.json
PYTHONPATH="$PWD" ryu-manager mininet.controller_static --ofp-tcp-listen-port 6653 &
sudo -n -E env PYTHONPATH="$PWD" .venv/bin/python -u scripts/run_gd4cl_ab.py --blocks 8
# bật lại Ryu như trên, rồi:
sudo -n -E env PYTHONPATH="$PWD" .venv/bin/python -u scripts/run_gd4cl_dinh_vi.py
```

Hai runner này ghi `results/report/gd4cl_ab.json` và `gd4cl_c1.json` và từ chối chạy nếu tệp
đã có, nên trên bản clone của repo hãy dùng `chay_vong_kin.sh`.
