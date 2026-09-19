# Phase 7.7 — Đóng băng, nghiệm thu và phán quyết

## 0. Dự đoán cho chiến dịch nghiệm thu (khóa TRƯỚC khi chạy)

Mục này được commit trước commit đóng băng, nên thứ tự "dự đoán → đóng băng → đo" được
git chứng minh. Code runtime chỉ đổi rất ít so với các lần đo trước, nên dự đoán bám sát
giá trị cũ.

| SLO | Giá trị trước (receipt, commit) | Dự đoán nghiệm thu |
|---|---|---|
| S12 `kill_to_stale.max_ms` | 3093 ms (`9bd5890`, 7.4) | 2.9–3.4 s, PASS (≤ 5000 ms) |
| S4 `s4_like_from_cmd.p95_ms` | 1770.8 ms (`3b666d5`, 7.5) | 1.6–1.9 s, PASS (≤ 3000 ms) |
| S5 block ON xấu nhất (p95) | 1.64 ms (`b30fee8`, 7.6) | 1.4–2.2 ms, PASS (≤ 50 ms) |
| S6_v2 `delta_mib` | 0.5625 MiB (`5be681f`, 7.7p1) | 0.3–0.8 MiB, PASS (≤ 1.0 MiB) |
| S11 `log_first` act | 0/4 (`b30fee8`) | 0/4, PASS; `log_late` 1 alarm / 0 act mỗi lần; `no_log` 4/4 act |
| e2e p95 / twin → UI p95 | 1469 / 44 ms (`3b666d5`) | 1.3–1.6 s / 30–60 ms |

Dự đoán cho quy tắc phát hành (amendment 3): `released = G1 ∧ G2 ∧ G3 ∧ G4 = true`, và
`fails_declared = ["S1"]`. S1 là giới hạn của 6R (envelope-only 0.30 < 0.875), không phải
một gate.

Nếu có dòng FAIL: ghi FAIL, truy tầng bằng bảng phân rã 7.5, sửa logic, tạo đóng băng mới
(`phase-7-frozen-2`) rồi đo lại. Toàn bộ lịch sử được giữ trong `history`. Không chỉnh
`ttlTicks` hay bất kỳ ngưỡng nào.

## 1. Quy trình

1. Commit code nghiệm thu và mục 0 → `build_phase7_freeze.py` → commit → tag `phase-7-frozen`.
2. `run_phase7_acceptance.py` chạy lại 5 phép đo live trên commit đóng băng. Trước mỗi bước:
   kiểm HEAD == tag, worktree sạch, SHA từng file == `phase7_freeze.json`; bảo đảm Ryu lắng
   nghe ở 6653 (mỗi harness kết thúc bằng `mn -c`, lệnh này kill cả `ryu-manager`).
3. `build_phase7_verdicts.py` suy bảng 14 dòng và gate bằng code (`measurements/phase7_verdicts.py`).
4. `build_phase7_manifest.py` niêm phong thứ tự đăng ký (lấy từ git) → tag `phase-7-complete`.

Kết quả nghiệm thu được điền vào các mục sau khi chạy xong.
