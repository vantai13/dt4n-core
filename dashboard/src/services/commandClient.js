// ---------------------------------------------------------------------------
// commandClient.js — TẦNG DỊCH VỤ gửi LỆNH (chiều XUỐNG). LỚP 4.
// Song song với dittoClient.js (đọc state) và sseClient.js (nghe state).
// Đây là "kênh gửi" mới — POST message tới controller Thing.
//
// TRÁCH NHIỆM DUY NHẤT: gói lệnh thành HTTP POST đúng giao thức 4.1, sinh
//   correlation-id, trả response ①. KHÔNG biết gì về vẽ/merge (việc của App.vue).
// ---------------------------------------------------------------------------

import { logUi } from './debugLog.js'

const NAMESPACE = import.meta.env.VITE_DITTO_NAMESPACE || 'org.dt4n'
const DITTO_PREFIX = '/ditto/api/2'
const CONTROLLER = `${NAMESPACE}:controller`
const COMMAND_ACK_TIMEOUT_SECONDS = 0

// Sinh correlation-id duy nhất mỗi lệnh để trace xuyên UI/Ditto/Agent/log.
// crypto.randomUUID có sẵn trong trình duyệt hiện đại.
export function newCommandCorrelationId() {
  return (crypto?.randomUUID?.() || 'cmd-' + Date.now() + '-' + Math.random())
}

// Gửi MỘT lệnh theo kiểu fire-and-forget. Dashboard không chờ live response vì
// kết quả thật vẫn là SSE state (kênh nhận), App.vue quan sát riêng.
export async function sendCommand(subject, target, params = {}, correlationId = null) {
  const cid = correlationId || newCommandCorrelationId()
  const url = `${DITTO_PREFIX}/things/${CONTROLLER}/inbox/messages/${subject}`
         + `?timeout=${COMMAND_ACK_TIMEOUT_SECONDS}`
  const body = { target, ...params, clientCorrelationId: cid }
  const startedAt = performance.now()

  logUi('command.send.start', {
    correlationId: cid,
    subject,
    target,
    params,
    url,
    timeoutSeconds: COMMAND_ACK_TIMEOUT_SECONDS,
  })

  let response = null
  let res = null
  let rawText = ''
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'correlation-id': cid,
      },
      body: JSON.stringify(body),
    })
    rawText = await res.text()
    try { response = rawText ? JSON.parse(rawText) : null } catch (_) { /* có thể rỗng */ }
  } catch (e) {
    logUi('command.send.network_error', {
      correlationId: cid,
      subject,
      target,
      error: e.message,
      durationMs: Math.round(performance.now() - startedAt),
    }, 'error')
    return { ok: false, timedOut: false, rejected: false,
             correlationId: cid, response: null, error: e.message }
  }

  // Với timeout=0, Ditto trả 202 ngay khi nhận message. App.vue vẫn quan sát
  // state qua SSE để quyết định kết quả thật.
  const timedOut = res.status === 408
  const rejected = response?.status === 'rejected'
  logUi('command.send.response', {
    correlationId: cid,
    subject,
    target,
    httpStatus: res.status,
    httpOk: res.ok,
    timedOut,
    rejected,
    durationMs: Math.round(performance.now() - startedAt),
    response,
    rawText: rawText.slice(0, 500),
  }, timedOut || rejected || !res.ok ? 'warn' : 'info')

  return {
    ok: res.ok && !rejected,
    timedOut,
    rejected,
    correlationId: cid,
    response,
    httpStatus: res.status,
  }
}
