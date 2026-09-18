# Hợp đồng bàn giao Phase 6R → Phase 7

## Phase 7 được gọi đúng ba thứ

```python
from ml.release import DetectorRelease
from ml.intervention_log import InMemoryInterventionLog

release = DetectorRelease.load("models/detector-release-1.0.0.json")
log = InMemoryInterventionLog()
scorer, fsm = release.build(log)

for snapshot in collector_stream():
    reading = scorer.observe(snapshot)
    transition = fsm.step(reading)
    if transition.state != "normal":
        body = release.payload(transition, reading, detected_at=now_iso())
        patch_ditto(body)
```

Một cặp scorer/FSM chỉ phục vụ một luồng snapshot liên tục.

## Phase 7 không được

1. Tự tạo `FastOnlineScorer`/`DetectorFSM` hoặc tự đặt mode, FSM params hay
   collector version.
2. Tính lại feature, threshold hoặc state ở Ditto, SSE hay Vue.
3. Suy state từ evidence. State có hysteresis; `suspect` với evidence false
   trong quiet window là đúng.
4. Tái dùng scorer/FSM sau restart; phải tạo cặp mới.
5. Đọc R-set/R-N để chọn ngưỡng guard vùng vận hành.
6. Cho controller hành động chỉ từ `evidence.conservation`; residual chỉ dẫn
   tới suspect, không bao giờ act.

## Payload

`state`, `reason`, `cause`, `detectedAt`, `modelVersion`, `artifactSha256`,
`releaseVersion`, `releaseSha256`, `conservationSha256`, và
`evidence{envelope, conservation, act_rule}`. Evidence mô tả tick hiện tại;
state có quán tính tối đa `release_m=3` tick.

## Nghĩa vụ Phase 7

- Đóng S12: detector chết thì twin stale trong ≤5 s.
- Đo S11 live với controller và InterventionLog thật.
- Preregister guard vùng vận hành, lấy ngưỡng từ train Phase 5.
- Đo tranh chấp CPU khi detector chạy cạnh Mininet/Ditto.
- Giữ ngân sách envelope 2 s + twin/UI ≤1 s + quan sát 1 s; công bố residual
  là kênh chậm khoảng 11 s.
