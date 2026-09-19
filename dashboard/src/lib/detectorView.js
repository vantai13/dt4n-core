// Phase 7.4: severity chỉ là ánh xạ của (decision.state, stale).
// Evidence chỉ tạo nhãn giải thích, không tham gia quyết định mức độ.
import { isStale } from './freshness.js'
import { shortName } from './translate.js'

export const DETECTOR_SEVERITY = Object.freeze({
  act: 'critical', suspect: 'warning', unknown: 'unknown',
  warming_up: 'unknown', normal: null,
})

const STATE_LABEL = Object.freeze({
  act: 'HÀNH ĐỘNG', suspect: 'NGHI NGỜ', unknown: 'CHƯA ĐÁNH GIÁ',
  warming_up: 'ĐANG KHỞI ĐỘNG', normal: 'BÌNH THƯỜNG',
})

function properties(thing, feature) {
  return thing?.features?.[feature]?.properties ?? {}
}

function channelLabel(evidence, state) {
  if (state !== 'suspect' && state !== 'act') return ''
  const fast = evidence.envelope || evidence.actRule
  if (fast && evidence.conservation) return 'kênh nhanh + kênh chậm'
  if (fast) return 'kênh nhanh (envelope, ~2 s)'
  if (evidence.conservation) return 'kênh chậm (residual, ~11 s)'
  return 'đang giữ trạng thái (hysteresis)'
}

export function severityOf(state, stale) {
  if (stale) return 'stale'
  return Object.prototype.hasOwnProperty.call(DETECTOR_SEVERITY, state)
    ? DETECTOR_SEVERITY[state]
    : 'unknown'
}

export function detectorView(thing, tracker, nowMs, graph = { nodes: [], edges: [] }) {
  const decision = properties(thing, 'decision')
  const freshness = properties(thing, 'freshness')
  const evidence = properties(thing, 'evidence')
  const stale = !thing || isStale(tracker, freshness, nowMs)
  const state = decision.state ?? 'unknown'
  const known = new Set([...graph.nodes.map(n => n.id), ...graph.edges.map(e => e.id)])
  const affected = Array.isArray(evidence.affected) ? evidence.affected.map(shortName) : []
  const alarming = !stale && (state === 'suspect' || state === 'act')
  return {
    present: !!thing,
    stale,
    state,
    stateLabel: stale ? 'KHÔNG XÁC NHẬN ĐƯỢC' : (STATE_LABEL[state] ?? state),
    severity: severityOf(state, stale),
    cause: decision.cause ?? '',
    reason: decision.reason ?? '',
    channel: channelLabel(evidence, state),
    lastConfirmedAgoMs: tracker.confirmedAt === null ? null : Math.max(0, nowMs - tracker.confirmedAt),
    highlight: alarming ? affected.filter(id => known.has(id)) : [],
    unmatched: alarming ? affected.filter(id => !known.has(id)) : [],
    unattributed: alarming ? (evidence.unattributed ?? 0) : 0,
    dropped: freshness.dropped ?? 0,
  }
}

export function allClear(deviceAlertCount, view) {
  return deviceAlertCount === 0 && view.present && !view.stale && view.state === 'normal'
    && !view.cause
}
