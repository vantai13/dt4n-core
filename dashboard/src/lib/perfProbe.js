import { nextTick } from 'vue'

const MAX = 500
const ENABLED = typeof window !== 'undefined'
  && new URLSearchParams(window.location.search).has('perf')

function buffer() {
  if (!window.__dt4nPerf) window.__dt4nPerf = []
  return window.__dt4nPerf
}

export function perfEnabled() {
  return ENABLED
}

export function markDetectorChange({ bootId, seq, state, source, t4 }) {
  if (!ENABLED) return
  const rec = { bootId, seq, state, source, t4, tDom: null, t5: null }
  const buf = buffer()
  buf.push(rec)
  if (buf.length > MAX) buf.splice(0, buf.length - MAX)
  nextTick(() => {
    rec.tDom = performance.now()
    requestAnimationFrame(() => requestAnimationFrame(() => {
      rec.t5 = performance.now()
    }))
  })
}
