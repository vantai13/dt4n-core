// Phase 8.5: controlView chỉ là ÁNH XẠ của (mode, stale) từ Thing controlloop.
//
// KHÔNG đọc capacity.bwMbps để suy "đang giới hạn". bwMbps là HIỆN THỰC;
// controlloop.mode là Ý ĐỊNH. Ba trường hợp chúng khác nhau, cả ba đều xảy ra
// thật trong hệ này:
//   1. người vận hành gửi setBandwidth tay  -> bw thấp, mode = IDLE
//   2. lệnh còn trên đường (p50 667 ms, 8.4) -> mode = MITIGATING, bw vẫn 20
//   3. lease hết hạn, watchdog phục hồi      -> bw = 20, controller kẹt MITIGATING
// Suy từ bwMbps sẽ nói dối ở cả ba.
import { isStale } from './freshness.js'

export const CONTROL_SEVERITY = Object.freeze({
  IDLE: null,             // không có gì để báo
  MITIGATING: 'active',   // đang can thiệp
  PROBING: 'active',      // đã gỡ nhưng episode CHƯA kết thúc -> vẫn "đang có chuyện"
  HOLD: 'warning',        // controller tự nguyện rút lui -> lúc cần con người nhất
})

const MODE_LABEL = Object.freeze({
  IDLE: 'RẢNH',
  MITIGATING: 'ĐANG GIẢM THIỂU',
  PROBING: 'ĐANG THĂM DÒ',
  HOLD: 'TẠM DỪNG',
})

const MODE_DETAIL = Object.freeze({
  IDLE: 'Không có can thiệp nào đang mở.',
  MITIGATING: 'Đang giới hạn băng thông nguồn gây nghẽn.',
  PROBING: 'Đã gỡ giới hạn, đang quan sát xem sự cố còn hay hết.',
  HOLD: 'Trạng thái detector không đáng tin — controller ngừng ra quyết định mới.',
})

function properties(thing, feature) {
  return thing?.features?.[feature]?.properties ?? {}
}

export function controlSeverityOf(mode, stale) {
  if (stale) return 'stale'
  // mode lạ = dashboard cũ gặp controller mới. Phải nói "tôi không hiểu",
  // KHÔNG được im lặng coi như IDLE (forward compatibility an toàn).
  return Object.prototype.hasOwnProperty.call(CONTROL_SEVERITY, mode)
    ? CONTROL_SEVERITY[mode]
    : 'unknown'
}

export function controlView(thing, tracker, nowMs, receivedAtMs = nowMs) {
  const decision = properties(thing, 'decision')
  const schedule = properties(thing, 'schedule')
  const freshness = properties(thing, 'freshness')
  const stale = !thing || isStale(tracker, freshness, nowMs)
  // thiếu dữ liệu -> HOLD, KHÔNG phải IDLE. Cùng nguyên tắc fail-safe với
  // initial_controlloop_body (hợp đồng D, 8.3).
  const mode = decision.mode ?? 'HOLD'

  // Đếm ngược bằng đồng hồ CỦA CHÍNH TRÌNH DUYỆT, neo vào lúc nhận.
  // holdRemainingS là KHOẢNG (hợp đồng D) nên không cần đồng bộ đồng hồ:
  // sai số = độ trễ mạng (~22 ms), không phụ thuộc lệch đồng hồ.
  // STALE -> NGỪNG đếm: đếm ngược từ một bản tin đã chết là nói dối có chủ đích.
  const elapsedS = Math.max(0, (nowMs - receivedAtMs) / 1000)
  const countdown = (value) =>
    stale ? null : Math.max(0, (Number(value) || 0) - elapsedS)

  const target = decision.target || ''
  return {
    present: !!thing,
    stale,
    mode,
    modeLabel: stale ? 'KHÔNG XÁC NHẬN ĐƯỢC' : (MODE_LABEL[mode] ?? mode),
    modeDetail: stale
      ? 'Không nhận được nhịp tim của controller.'
      : (MODE_DETAIL[mode] ?? 'Chế độ lạ — dashboard này không hiểu.'),
    severity: controlSeverityOf(mode, stale),
    target,
    limitMbps: Number(decision.limitMbps) || 0,
    holdRemainingS: countdown(schedule.holdRemainingS),
    probeRemainingS: countdown(schedule.probeRemainingS),
    attempt: Number(schedule.attempt) || 0,
    episode: Number(schedule.episode) || 0,
    reason: decision.reason ?? '',
    lastConfirmedAgoMs:
      tracker?.confirmedAt == null ? null : Math.max(0, nowMs - tracker.confirmedAt),
    // Mục tiêu giảm thiểu -> KÊNH THỊ GIÁC RIÊNG (🛡 + nét đứt), KHÔNG trộn với
    // kênh "detector nêu tên" (⚑ + viền dày) của Phase 7. Một biến dữ liệu một
    // kênh; nhồi hai biến vào một kênh là mất thông tin.
    shielded: (!stale && mode === 'MITIGATING' && target)
      ? [target, target + '-s1']
      : [],
  }
}

export function allClear(deviceAlertCount, detector, control) {
  return deviceAlertCount === 0
    && detector.present && !detector.stale
    && detector.state === 'normal' && !detector.cause
    // --- MỚI ở 8.5 ---
    && !!control && control.present   // chưa bootstrap Thing -> không được nói "ổn"
    && !control.stale                 // chống masking: detector sống che controller chết
    && control.mode === 'IDLE'        // `normal` khi đang MITIGATING là do CHÍNH nó tạo ra
}

// Quan sát bị thu hẹp: ÁNH XẠ từ `cause` do CHÍNH detector công bố, không suy diễn.
// Trung thực về mức độ: 8.3 đo được 1/3 round dưới flood KHÔNG bị ức chế
// (link-s2-s3 nằm ngoài vùng 15/16), nên nhãn nói "thu hẹp", không nói "mù".
export function observabilityNote(detector) {
  if (!detector || detector.stale) return null
  if (detector.cause !== 'suppressed_intervention') return null
  return {
    level: 'caution',
    label: 'QUAN SÁT BỊ THU HẸP',
    detail: 'Đang có can thiệp mở — cảm biến bỏ qua vùng ảnh hưởng của nó.',
  }
}
