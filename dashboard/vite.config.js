import { fileURLToPath, URL } from 'node:url'
import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// ---------------------------------------------------------------------------
// vite.config.js — Cấu hình dev server + PROXY sang Ditto.
//
// VẤN ĐỀ file này giải quyết (xem Lesson 3.2, Phần 2.3):
//   - Browser chạy dashboard ở localhost:5173; Ditto ở localhost:8080.
//     Khác cổng = khác origin -> browser CHẶN request (CORS).
//   - Không muốn nhét user/password Ditto vào code frontend (lộ mật khẩu).
//
// GIẢI PHÁP: proxy. Browser gọi '/ditto/...' (CÙNG origin -> không CORS).
//   Vite âm thầm chuyển tiếp sang Ditto :8080, tự gắn Basic Auth ở tầng server
//   (server-to-server, không bị luật browser ràng buộc). Mật khẩu KHÔNG lọt
//   xuống browser -> đúng pattern "backend-for-frontend" của production.
// ---------------------------------------------------------------------------

const REPO_ROOT = fileURLToPath(new URL('..', import.meta.url))
const UI_LOG_PATH = path.join(REPO_ROOT, 'logs', 'dashboard_ui.jsonl')
const FLOW_LOG_PATH = path.join(REPO_ROOT, 'logs', 'command_flow.log')
const AUDIT_LOG_PATH = path.join(REPO_ROOT, 'logs', 'command_agent_audit.log')

function compactJson(value) {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch (_) {
    return String(value)
  }
}

function localTimestamp() {
  const d = new Date()
  const pad = (n, w = 2) => String(n).padStart(w, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
       + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.`
       + `${pad(d.getMilliseconds(), 3)}`
}

function flowLine(row) {
  const cid = row.correlationId || '-'
  const subject = row.subject || '-'
  const target = row.target || '-'
  const prefix = `[${localTimestamp()}] [UI] [cid=${cid}]`

  if (row.event === 'command.ui.click') {
    return [
      '',
      '================================================================================',
      `${prefix} CLICK subject=${subject} target=${target} stateBefore=${row.stateBefore || '-'} params=${compactJson(row.params) || '{}'}`,
    ].join('\n')
  }
  if (row.event === 'command.send.start') {
    return `${prefix} SEND  POST ${row.url} timeout=${row.timeoutSeconds}s`
  }
  if (row.event === 'command.send.response') {
    const err = row.response?.error || ''
    const msg = row.response?.message || row.rawText || ''
    return `${prefix} DITTO_RESPONSE http=${row.httpStatus} timedOut=${row.timedOut} rejected=${row.rejected} durationMs=${row.durationMs} error=${err} message=${msg}`
  }
  if (row.event === 'command.ui.ack') {
    return `${prefix} UI_ACK ok=${row.ok} timedOut=${row.timedOut} rejected=${row.rejected} http=${row.httpStatus}`
  }
  if (row.event === 'command.reflect.wait_start') {
    return `${prefix} WAIT_STATE target=${target} expect=${row.expect} current=${row.stateNow || '-'} timeoutMs=${row.timeoutMs}`
  }
  if (row.event === 'command.reflect.success') {
    return `${prefix} STATE_OK target=${target} expect=${row.expect} state=${row.state}`
  }
  if (row.event === 'command.reflect.success_after_resync') {
    return `${prefix} STATE_OK_AFTER_RESYNC target=${target} expect=${row.expect} state=${row.state}`
  }
  if (row.event === 'command.reflect.timeout') {
    return `${prefix} STATE_TIMEOUT target=${target} expect=${row.expect} state=${row.state || '-'}`
  }
  if (row.event === 'command.reflect.skipped') {
    return `${prefix} STATE_SKIP subject=${subject} target=${target}`
  }
  if (row.event === 'command.send.network_error' || row.event === 'command.ui.error') {
    return `${prefix} ERROR event=${row.event} subject=${subject} target=${target} message=${row.error || '-'} durationMs=${row.durationMs || '-'}`
  }
  if (row.event === 'topology.load.start') {
    return `[${localTimestamp()}] [UI] TOPOLOGY_LOAD_START`
  }
  if (row.event === 'topology.load.done') {
    return `[${localTimestamp()}] [UI] TOPOLOGY_LOAD_DONE`
  }
  if (row.event === 'topology.load.error') {
    return `[${localTimestamp()}] [UI] TOPOLOGY_LOAD_ERROR message=${row.error || '-'}`
  }
  if (row.event === 'sse.open') {
    return `[${localTimestamp()}] [UI] SSE_OPEN`
  }
  if (row.event === 'sse.error') {
    return `[${localTimestamp()}] [UI] SSE_ERROR`
  }
  if (row.event === 'state.resync.done') {
    return `[${localTimestamp()}] [UI] RESYNC_DONE reason=${row.reason || '-'} things=${row.things} nodes=${row.nodes} edges=${row.edges} durationMs=${row.durationMs}`
  }

  return `[${localTimestamp()}] [UI] event=${row.event || '-'} level=${row.level || 'info'} data=${compactJson(row)}`
}

function appendFlowLog(row, callback) {
  const line = flowLine(row) + '\n'
  fs.mkdirSync(path.dirname(FLOW_LOG_PATH), { recursive: true })
  fs.appendFile(FLOW_LOG_PATH, line, { mode: 0o666 }, (err) => {
    if (!err) {
      fs.chmod(FLOW_LOG_PATH, 0o666, () => {})
    }
    callback(err)
  })
}

function dashboardUiLogPlugin() {
  return {
    name: 'dt4n-dashboard-ui-log',
    configureServer(server) {
      server.middlewares.use('/_dt4n/ui-log', (req, res, next) => {
        if (req.method !== 'POST') return next()

        let body = ''
        req.setEncoding('utf8')
        req.on('data', (chunk) => {
          body += chunk
          if (body.length > 64 * 1024) {
            res.statusCode = 413
            res.end('log payload too large')
            req.destroy()
          }
        })
        req.on('end', () => {
          let payload = {}
          try {
            payload = body ? JSON.parse(body) : {}
          } catch (e) {
            payload = {
              event: 'ui_log.parse_error',
              level: 'warn',
              parseError: e.message,
              raw: body.slice(0, 2000),
            }
          }

          const row = {
            tsServer: new Date().toISOString(),
            source: 'dashboard',
            ...payload,
          }

          fs.mkdirSync(path.dirname(UI_LOG_PATH), { recursive: true })
          fs.appendFile(UI_LOG_PATH, JSON.stringify(row) + '\n', (err) => {
            if (err) {
              server.config.logger.warn(`Không ghi được UI log: ${err.message}`)
              res.statusCode = 500
              res.end('log write failed')
              return
            }
            fs.chmod(UI_LOG_PATH, 0o666, () => {})
            appendFlowLog(row, (flowErr) => {
              if (flowErr) {
                server.config.logger.warn(`Không ghi được command flow log: ${flowErr.message}`)
                res.statusCode = 500
                res.end('flow log write failed')
                return
              }
              res.statusCode = 204
              res.end()
            })
          })
        })
      })

      server.middlewares.use('/_dt4n/history', (req, res, next) => {
        if (req.method !== 'GET') return next()

        fs.readFile(AUDIT_LOG_PATH, 'utf8', (err, data) => {
          res.setHeader('Content-Type', 'application/json')
          if (err) {
            res.end(JSON.stringify({ entries: [] }))
            return
          }

          const lines = data.split('\n').filter(Boolean).slice(-200)
          const entries = []
          for (const line of lines) {
            try {
              entries.push(JSON.parse(line))
            } catch (_) {
              // Bỏ qua dòng log hỏng để History vẫn mở được.
            }
          }
          res.end(JSON.stringify({ entries: entries.reverse() }))
        })
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  // Đọc biến môi trường từ file .env (KHÔNG hardcode host/mật khẩu vào code).
  const env = loadEnv(mode, process.cwd(), '')

  const DITTO_URL  = env.DITTO_URL  || 'http://localhost:8080'
  const DITTO_USER = env.DITTO_USER || 'ditto'
  const DITTO_PASS = env.DITTO_PASSWORD || 'ditto'
  const DITTO_PRE_AUTH = env.DITTO_PRE_AUTH || `nginx:${DITTO_USER}`

  // Tạo chuỗi Basic Auth: "Basic base64(user:pass)". Đây là cách HTTP mã hóa
  // cặp user/pass để gửi trong header Authorization (KHÔNG phải mã hóa bảo mật,
  // chỉ là encode -> vì thế mới cần giấu ở tầng server, không phơi ra browser).
  const basicAuth = 'Basic ' + Buffer.from(`${DITTO_USER}:${DITTO_PASS}`).toString('base64')

  // TỰ PHÁT HIỆN chế độ bypass: chỉ khi trỏ THẲNG gateway (cổng 8081) mới gửi
  // x-ditto-pre-authenticated. Khi đi qua nginx (8080), theo Ditto docs client
  // KHÔNG được tự set header đó — nginx là bên DUY NHẤT set nó. Gửi thừa có thể
  // bị nginx từ chối (security hardening coi là giả mạo).
  const isBypass = /:8081(\/|$)/.test(DITTO_URL)

  // Hàm gắn auth đúng theo chế độ -> dùng chung cho cả 2 đường proxy (DRY).
  function attachAuth(proxyReq) {
    if (isBypass) {
      // Bypass gateway :8081 (dev/lab, khi nginx lỗi) -> tự đóng vai nginx.
      proxyReq.setHeader('x-ditto-pre-authenticated', DITTO_PRE_AUTH)
    } else {
      // Chuẩn: qua nginx :8080 -> chỉ gửi Basic Auth, để nginx tự set pre-auth.
      proxyReq.setHeader('Authorization', basicAuth)
    }
  }

  return {
    plugins: [vue(), dashboardUiLogPlugin()],

    resolve: {
      // Cho phép viết '@/components/...' thay vì đường dẫn tương đối dài dòng.
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },

    server: {
      host: 'localhost',
      port: 5173,

      proxy: {
        // ⚠️ THỨ TỰ QUAN TRỌNG: '/ditto-sse' PHẢI đứng TRƯỚC '/ditto'.
        // Vì Vite khớp proxy theo TIỀN TỐ (startsWith) và dùng cái khớp ĐẦU TIÊN.
        // Chuỗi '/ditto-sse/...' cũng bắt đầu bằng '/ditto', nên nếu '/ditto'
        // đứng trước, nó sẽ NUỐT luôn request SSE -> rewrite sai -> 404 -> OFFLINE.
        // Nguyên tắc: prefix CỤ THỂ hơn (dài hơn) phải xét TRƯỚC prefix tổng quát.

        // === Đường SSE (streaming, kết nối sống lâu, không buffer/timeout) ===
        '/ditto-sse': {
          target: DITTO_URL,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/ditto-sse/, ''),
          timeout: 0,
          proxyTimeout: 0,
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              attachAuth(proxyReq)
              proxyReq.setHeader('X-Accel-Buffering', 'no')   // nginx đừng đệm SSE
              proxyReq.setHeader('Cache-Control', 'no-cache')
              proxyReq.setHeader('Accept-Encoding', 'identity')
            })
          },
        },

        // === Đường request THƯỜNG (fetch, Search API) ===
        '/ditto': {
          target: DITTO_URL,        // đích thật (nginx :8080, hoặc gateway :8081 khi bypass)
          changeOrigin: true,       // sửa header Host cho khớp đích
          rewrite: (path) => path.replace(/^\/ditto/, ''),
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              attachAuth(proxyReq)
            })
          },
        },
      },
    },
  }
})
