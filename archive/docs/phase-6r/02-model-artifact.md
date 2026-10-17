# Lesson 6R.2 — Model artifact: serialization, version và schema guard

Artifact: `models/envelope-1.0.0.json`  
Receipt: `results/report/phase6r_artifact_equivalence.json`  
Artifact `content_sha256`: `4741e405c03c17f6074d259ba9c9e1a0458a96721e86d2b9679bf7df05f4352b`

## 1. Kết quả

Envelope detector đã được chuyển từ pipeline thí nghiệm thành một artifact JSON
tự chứa và nạp được mà không cần fit lại:

```text
n_columns = 71
version = envelope-1.0.0
E = 8.968806422101116

Tier A primary_k          590/590 bit-exact
Tier A secondary_excess   590/590 bit-exact
Tier A secondary_dual     590/590 bit-exact
Tier A ablation_loss_only 590/590 bit-exact

Tier B k=True excess=True judgeable=True max|diff|=0.0
```

Artifact chứa 71 cặp bounds, bốn họ feature, các threshold đóng băng và 16 cặp
`link_stats`. Nó ghi rõ scorer không dùng delta, không cần warmup feature và bắt
buộc dùng `link_stats_mode=frozen`.

## 2. Ranh giới fit/serve

Phase 6 là đường fit/thí nghiệm: đọc toàn bộ run, kiểm sidecar, tạo aggregate,
chọn feature và fit bounds. Phase 7 chỉ được nạp một file và chấm snapshot mới.
`EnvelopeModel.load()` vì vậy chỉ đọc, kiểm hash/schema và dựng vector; nó không
đọc `data/`, không gọi `load_split()` và không fit bất kỳ đại lượng nào.

Artifact dùng JSON thay vì pickle để đọc được bằng mắt, diff được bằng Git,
không gắn với object/version sklearn và không có rủi ro thực thi mã khi nạp.

## 3. Cấu trúc và provenance

`content_sha256` là sibling của `content`, không nằm trong chính vùng được băm.
Điều này tránh bài toán fixed point của self-hash. `content` được canonicalize
bằng `sort_keys=True` và separator ổn định trước khi SHA-256.

Provenance ghim:

- 8 train run IDs và số dòng fit envelope.
- SHA file manifest và ticks CSV.
- Content SHA của CV, amendment 1, Phase 6 envelope và SLO 6R.1.
- SHA code `ml/detectors/envelope.py`.
- Git commit tại thời điểm build.

Liên kết `slo_content_sha256` tạo provenance hai chiều: model biết bộ SLO nào sẽ
đo nó, còn SLO đã ghim các artifact Phase 6 dùng làm cơ sở.

## 4. Hai tầng tương đương

### 4.1 Tier A — decision layer

Ticks CSV có 14 cột output, không có 71 giá trị feature. Nó đủ kiểm tra:

- Giá trị E/K đã đóng băng.
- Phép so sánh strict `excess > E`.
- Unknown bị mask khỏi alarm.
- Luật act dùng OR giữa indicator và rate-shared.

Tier A chạy từ artifact và receipt đã commit, không cần raw.

### 4.2 Tier B — scoring layer

Tier B cần ma trận feature 590×71. Repo có đủ 18 raw JSONL với tổng kích thước
8.7 MiB, nên chọn Option 0: commit nguyên bản dữ liệu, không nén, để giữ SHA khớp
sidecar và để clone sạch chạy được toàn bộ kiểm tra.

Tier B tái tạo feature matrix bằng pipeline Phase 6 rồi so `k`, `excess`,
`judgeable`, `k_indicator` và `k_rate`. Tất cả đều bit-exact.

### 4.3 Phát hiện về parser float CSV

Lần build đầu, scorer mới khớp bit-exact với `ml.detectors.envelope.score`, nhưng
so với `pandas.read_csv()` mặc định cho `max|diff|=4.547473508864641e-13` trên
28 dòng. Nguyên nhân không phải thứ tự cộng: parser nhanh mặc định của pandas đã
làm tròn các chuỗi float trong CSV. Đọc bằng Python `float()` hoặc pandas với
`float_precision="round_trip"` khôi phục đúng bits và cho `max|diff|=0.0`.

Build và test đã ghim `float_precision="round_trip"`; không dùng epsilon để che
sai khác này.

## 5. Schema guard

Artifact từ chối khi:

- Thiếu khóa bắt buộc hoặc sai schema version.
- Version không phải semver.
- Columns trùng, bounds thiếu/thừa/không finite hoặc `min > max`.
- Primary khác columns; indicator/rate chồng nhau hoặc không phủ đủ.
- Family có cột lạ hoặc thiếu threshold.
- Hash lệch do sửa nội dung hoặc đảo thứ tự columns.

Đầu vào được kiểm bất đối xứng có chủ đích: thiếu một trong 71 cột thì raise
`ArtifactError`; cột thừa được bỏ qua vì snapshot thực có nhiều metadata ngoài
feature model. `_matrix()` luôn chọn `frame[self.columns]`, nên thứ tự cột đầu
vào không ảnh hưởng kết quả.

Mọi dòng có ít nhất một feature không finite được đánh dấu `judgeable=False` và
không phát `suspect` hay `act`. Dữ liệu Phase 6 có đúng 8 dòng unknown: 4 dòng
`y=1` và 4 dòng `y=0`.

## 6. Version và bất biến

Version bắt đầu tại `envelope-1.0.0`:

- MAJOR: đổi tập input columns hoặc ngữ nghĩa state.
- MINOR: đổi bounds/threshold với cùng input contract.
- PATCH: chỉ đổi metadata/provenance, không đổi số model.

Builder từ chối ghi đè nếu file version hiện tại đã tồn tại. Mọi thay đổi model
phải tăng version và tạo file mới.

## 7. File và lệnh kiểm chứng

```bash
.venv/bin/python -m scripts.build_model_artifact
.venv/bin/python -m pytest test/test_model_artifact.py -v
.venv/bin/python -m pytest -q
```

Nguồn triển khai:

- `ml/model.py`: loader, schema guard, scoring và decision layer.
- `scripts/build_model_artifact.py`: dựng artifact từ các artifact Phase 6.
- `test/test_model_artifact.py`: round-trip, provenance, schema và Tier A/B.
- `results/report/phase6r_artifact_equivalence.json`: receipt máy đọc.
