const UI_LOG_ENDPOINT = '/_dt4n/ui-log'

let seq = 0

function safeStringify(row) {
  try {
    return JSON.stringify(row)
  } catch (e) {
    return JSON.stringify({
      tsClient: new Date().toISOString(),
      event: 'ui_log.stringify_error',
      level: 'warn',
      error: e.message,
    })
  }
}

export function logUi(event, data = {}, level = 'info') {
  const row = {
    tsClient: new Date().toISOString(),
    seq: ++seq,
    event,
    level,
    path: window.location.pathname,
    ...data,
  }
  const body = safeStringify(row)

  try {
    if (navigator.sendBeacon && body.length < 60000) {
      const blob = new Blob([body], { type: 'application/json' })
      if (navigator.sendBeacon(UI_LOG_ENDPOINT, blob)) return
    }
  } catch (_) {
    // Fall back to fetch below.
  }

  fetch(UI_LOG_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  }).catch(() => {
    // Logging must never break the dashboard flow.
  })
}
