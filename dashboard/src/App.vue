<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import TopologyView from './components/TopologyView.vue'
import InfoPanel from './components/InfoPanel.vue'
import AlertPanel from './components/AlertPanel.vue'
import HistoryPanel from './components/HistoryPanel.vue'
import { fetchAllThings } from './services/dittoClient.js'
import { openThingStream } from './services/sseClient.js'
import { sendCommand, newCommandCorrelationId } from './services/commandClient.js'
import { logUi } from './services/debugLog.js'
import { thingsToGraph, applyDelta } from './lib/translate.js'

// ---------------------------------------------------------------------------
// App.vue — ĐIỀU PHỐI (orchestrator). LỚP 4.
// Lesson 3.2: fetch -> dịch -> vẽ (tĩnh).
// Lesson 3.3: THÊM real-time — giữ STATE (thingsById), nghe SSE, merge delta,
//   re-sync khi reconnect. STATE là trung tâm: fetch dựng, delta merge vào,
//   đồ thị vẽ TỪ state (không bao giờ vẽ thẳng từ delta).
// ---------------------------------------------------------------------------

const graph = ref({ nodes: [], edges: [] })   // dữ liệu ĐÃ dịch, cho TopologyView
const status = ref('loading')
const errorMsg = ref('')
const live = ref(false)                        // đang nhận real-time?
const showHistory = ref(false)
const selectedNodeId = ref(null)
const selectedEdgeId = ref(null)
const cmdFeedback = ref('')

// STATE trung tâm: map thingId -> Thing đầy đủ. KHÔNG phải ref (không cần Vue
// theo dõi sâu map này); mỗi lần đổi ta dịch lại -> gán graph.value (ref) -> UI đổi.
let thingsById = {}
let reflectionToken = 0

const DEFAULT_REFLECTION_TIMEOUT_MS = 20000
const SWITCH_REFLECTION_TIMEOUT_MS = 45000

// Dựng lại state đầy đủ từ Ditto (dùng cho lần đầu VÀ mỗi lần re-sync).
async function resync(reason = 'manual') {
  const startedAt = performance.now()
  logUi('state.resync.start', { reason })
  try {
    const things = await fetchAllThings()      // FETCH snapshot đầy đủ
    thingsById = Object.fromEntries(things.map(t => [t.thingId, t]))
    rebuildGraph()
    logUi('state.resync.done', {
      reason,
      things: things.length,
      nodes: graph.value.nodes.length,
      edges: graph.value.edges.length,
      durationMs: Math.round(performance.now() - startedAt),
    })
  } catch (e) {
    logUi('state.resync.error', {
      reason,
      error: e.message,
      durationMs: Math.round(performance.now() - startedAt),
    }, 'error')
    throw e
  }
}

// Dịch state -> graph (đồ thị vẽ TỪ state, đây là điểm mấu chốt kiến trúc).
function rebuildGraph() {
  graph.value = thingsToGraph(Object.values(thingsById))
  status.value = graph.value.nodes.length ? 'ready' : 'error'
  if (!graph.value.nodes.length)
    errorMsg.value = 'Ditto không trả về Thing nào. Kiểm tra namespace / bootstrap / Sync Agent.'
}

async function loadTopology() {
  status.value = 'loading'
  logUi('topology.load.start')
  try {
    await resync('initial-load')               // snapshot ban đầu
    startStream()                              // rồi mới nghe delta
    logUi('topology.load.done')
  } catch (e) {
    status.value = 'error'
    errorMsg.value = e.message
    logUi('topology.load.error', { error: e.message }, 'error')
  }
}

// --- Real-time: mở SSE, xử lý 3 callback ---
let closeStream = null
function startStream() {
  if (closeStream) return                      // đã mở rồi -> không mở trùng
  closeStream = openThingStream({
    // Mỗi delta (Thing-mảnh) -> merge vào state -> dịch lại -> đồ thị đổi.
    onDelta: (partial) => {
      thingsById = applyDelta(thingsById, partial)   // MERGE (đã test kỹ)
      rebuildGraph()
    },
    // Kết nối (lại) OK -> RE-SYNC: lấy lại snapshot phòng khi bỏ lỡ delta lúc rớt.
    onOpen: async () => {
      live.value = true
      logUi('sse.open')
      try { await resync('sse-open') } catch (_) { /* giữ state cũ nếu re-sync lỗi tạm */ }
    },
    onError: () => {
      live.value = false
      logUi('sse.error', {}, 'warn')
    },                                         // EventSource sẽ tự thử lại
  })
}

onMounted(loadTopology)
onUnmounted(() => { if (closeStream) closeStream() })   // dọn kết nối khi rời trang

// Nhận sự kiện click từ TopologyView -> cho InfoPanel biết đang chọn gì.
const onNode = id => { selectedNodeId.value = id; selectedEdgeId.value = null }
const onEdge = id => { selectedEdgeId.value = id; selectedNodeId.value = null }
const onClear = () => { selectedNodeId.value = null; selectedEdgeId.value = null }

// Click một cảnh báo -> chọn đúng node/edge đó (nối AlertPanel với InfoPanel).
const onAlertFocus = (a) => {
  if (a.kind === 'node') onNode(a.id)
  else onEdge(a.id)
}

async function onCommand({ subject, target, params }) {
  cmdFeedback.value = 'Đã gửi, đang chờ mạng phản ánh...'
  const correlationId = newCommandCorrelationId()
  logUi('command.ui.click', {
    correlationId,
    subject,
    target,
    params,
    stateBefore: thingState(target),
  })

  const reflectPromise = watchForReflection(subject, target, params, correlationId)
    .catch((e) => {
      cmdFeedback.value = 'Lỗi quan sát trạng thái: ' + e.message
      logUi('command.reflect.error', {
        correlationId,
        subject,
        target,
        error: e.message,
      }, 'error')
    })

  sendCommand(subject, target, params, correlationId).then(({
    ok,
    timedOut,
    rejected,
    response,
    error,
    httpStatus,
  }) => {
    logUi('command.ui.ack', {
      correlationId,
      subject,
      target,
      ok,
      timedOut,
      rejected,
      httpStatus,
      response,
      error,
    }, ok || timedOut ? 'info' : 'warn')
    if (rejected) {
      reflectionToken++
      cmdFeedback.value = 'Bị từ chối: ' + (response?.result || response?.reason || 'lỗi')
      return
    }
    if (!ok && !timedOut) {
      cmdFeedback.value = 'Lỗi gửi lệnh: ' + (error || response?.message || 'lỗi')
    }
  }).catch((e) => {
    cmdFeedback.value = 'Lỗi gửi lệnh: ' + e.message
    logUi('command.ui.error', { subject, target, error: e.message }, 'error')
  })

  return reflectPromise
}

function thingState(target) {
  return thingsById[target]?.features?.status?.properties?.state
}

function thingBw(target) {
  return thingsById[target]?.features?.capacity?.properties?.bwMbps
}

async function watchForReflection(subject, target, params = {}, correlationId = null) {
  let matches = null
  let expectDesc = null
  let observed = () => null

  const STATE_EXPECT = {
    disableLink: 'down',
    enableLink: 'up',
    disableHost: 'down',
    enableHost: 'up',
    disableSwitch: 'down',
    enableSwitch: 'up',
  }

  if (subject in STATE_EXPECT) {
    const expect = STATE_EXPECT[subject]
    matches = () => thingState(target) === expect
    expectDesc = expect
    observed = () => thingState(target)
  } else if (subject === 'setBandwidth') {
    const want = Number(params?.bw)
    matches = () => {
      const cur = Number(thingBw(target))
      return Number.isFinite(cur) && Math.abs(cur - want) < 0.5
    }
    expectDesc = `bw=${params?.bw}`
    observed = () => thingBw(target)
  }

  if (!matches) {
    cmdFeedback.value = 'Đã gửi lệnh; chưa có trạng thái phản ánh trực tiếp.'
    logUi('command.reflect.skipped', { correlationId, subject, target })
    return
  }

  const token = ++reflectionToken
  const timeoutMs = subject === 'enableSwitch' || subject === 'disableSwitch'
    ? SWITCH_REFLECTION_TIMEOUT_MS
    : DEFAULT_REFLECTION_TIMEOUT_MS
  const deadline = Date.now() + timeoutMs
  logUi('command.reflect.wait_start', {
    correlationId,
    subject,
    target,
    expect: expectDesc,
    stateNow: observed(),
    timeoutMs,
  })
  while (Date.now() < deadline && token === reflectionToken) {
    if (matches()) {
      cmdFeedback.value = 'Thành công (mạng đã phản ánh).'
      logUi('command.reflect.success', {
        correlationId,
        subject,
        target,
        expect: expectDesc,
        state: observed(),
      })
      return
    }
    await new Promise(resolve => setTimeout(resolve, 500))
  }

  if (token !== reflectionToken) return

  try { await resync('command-reflection-timeout') } catch (_) { /* nếu resync lỗi, giữ cảnh báo bên dưới */ }
  if (matches()) {
    cmdFeedback.value = 'Thành công (mạng đã phản ánh).'
    logUi('command.reflect.success_after_resync', {
      correlationId,
      subject,
      target,
      expect: expectDesc,
      state: observed(),
    })
  } else {
    cmdFeedback.value = 'Cảnh báo: chưa thấy mạng phản ánh kết quả.'
    logUi('command.reflect.timeout', {
      correlationId,
      subject,
      target,
      expect: expectDesc,
      state: observed(),
    }, 'warn')
  }
}
</script>

<template>
  <div class="app">
    <header class="app-header">
      <span class="brand">Digital Twin — Network Dashboard</span>
      <div class="header-right">
        <button class="hist-toggle" @click="showHistory = true">🕑 Lịch sử</button>
        <span class="live" :class="{ on: live }">
          <span class="dot"></span>{{ live ? 'LIVE' : 'OFFLINE' }}
        </span>
      </div>
    </header>

    <div v-if="status === 'ready'" class="main">
      <TopologyView
        :graph="graph"
        @node-selected="onNode"
        @edge-selected="onEdge"
        @selection-cleared="onClear"
      />
      <div class="side">
        <AlertPanel :graph="graph" @focus="onAlertFocus" />
        <InfoPanel
          :graph="graph"
          :selectedNodeId="selectedNodeId"
          :selectedEdgeId="selectedEdgeId"
          :cmdFeedback="cmdFeedback"
          @command="onCommand"
        />
      </div>
    </div>

    <div v-else-if="status === 'loading'" class="center">
      <div class="spinner"></div><p>Đang tải topology từ Ditto…</p>
    </div>

    <div v-else class="center error">
      <div class="err-icon">⚠️</div>
      <h2>Không tải được topology</h2>
      <p>{{ errorMsg }}</p>
      <button class="reload" @click="loadTopology">↻ Thử lại</button>
    </div>

    <HistoryPanel v-if="showHistory" @close="showHistory = false" />
  </div>
</template>

<style>
body, html { margin: 0; height: 100%; font-family: Arial, sans-serif; background: #0f172a; }
.app { display: flex; flex-direction: column; height: 100vh; }
.app-header { display: flex; align-items: center; justify-content: space-between;
  height: 60px; padding: 0 1.5rem; border-bottom: 1px solid #334155; }
.brand { color: #00F7F7; font-size: 1.25rem; font-weight: 700;
  text-shadow: 0 0 8px rgba(0,247,247,0.4); }
.header-right { display: flex; align-items: center; gap: 14px; }
.hist-toggle { background: #1e293b; color: #00F7F7; border: 1px solid #334155;
  border-radius: 6px; padding: 6px 12px; font-weight: 700; cursor: pointer; }
.hist-toggle:hover { filter: brightness(1.25); }
.reload { background: #00F7F7; color: #0f172a; border: none; border-radius: 6px;
  padding: 6px 14px; font-weight: 600; cursor: pointer; }
.live { display: flex; align-items: center; gap: 6px; font-size: 0.8rem;
  font-weight: 700; letter-spacing: 1px; color: #64748b; }
.live.on { color: #22c55e; }
.live .dot { width: 9px; height: 9px; border-radius: 50%; background: #64748b; }
.live.on .dot { background: #22c55e; box-shadow: 0 0 8px #22c55e; animation: pulse 1.4s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
.main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.side {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
  background: #1e293b;
  border-left: 1px solid #334155;
  overflow: hidden;
}
.side > * { border-left: none; min-height: 0; }
.center { display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: calc(100vh - 60px); color: #94a3b8; gap: 1rem; padding: 2rem; text-align: center; }
.center.error h2 { color: #f87171; margin: 0; }
.err-icon { font-size: 3rem; }
.spinner { width: 48px; height: 48px; border: 4px solid #334155; border-top-color: #00F7F7;
  border-radius: 50%; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
