// Freshness phía consumer — bản song sinh JS của bridge/freshness.py.
// Lần đầu chỉ ARM; cùng boot phải tăng seq; boot đã nghỉ hưu bị từ chối.

export function createFreshness() {
  return { boot: null, seq: null, retired: new Set(), confirmedAt: null }
}

export function observeFreshness(tr, freshness, nowMs) {
  const boot = freshness?.bootId
  const seq = freshness?.seq
  if (!Number.isInteger(seq)) return false
  if (tr.boot === null) {
    tr.boot = boot
    tr.seq = seq
    return true
  }
  if (boot === tr.boot) {
    if (seq <= tr.seq) return false
  } else if (tr.retired.has(boot)) {
    return false
  } else {
    tr.retired.add(tr.boot)
  }
  tr.boot = boot
  tr.seq = seq
  tr.confirmedAt = nowMs
  return true
}

export function ttlMs(freshness) {
  return (freshness?.ttlTicks ?? 3) * (freshness?.tickIntervalMs ?? 1000)
}

export function isStale(tr, freshness, nowMs) {
  if (tr.confirmedAt === null) return true
  return (nowMs - tr.confirmedAt) > ttlMs(freshness)
}
