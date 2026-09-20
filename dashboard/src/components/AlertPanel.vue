<template>
  <div class="alert-panel">
    <h3>ALERTS <span class="count" :class="worstClass">{{ alerts.length }}</span></h3>

    <div class="detector" :class="detector.severity || 'ok'"
         :data-detector-freshness="detector.stale ? 'stale' : 'fresh'"
         :data-detector-state="detector.state">
      <div class="det-line">
        <span class="sev-dot"></span>
        <span class="who">Detector</span>
        <span class="det-state">{{ detector.stateLabel }}</span>
      </div>
      <div v-if="detector.stale" class="det-sub">
        {{ detector.lastConfirmedAgoMs === null
            ? 'chưa từng nhận nhịp tim mới từ lúc mở trang'
            : 'nhịp tim mới cuối cùng ' + (detector.lastConfirmedAgoMs / 1000).toFixed(1) + ' s trước' }}
      </div>
      <div v-else-if="detector.channel" class="det-sub">{{ detector.channel }}</div>
      <div v-if="!detector.stale && detector.cause" class="det-sub">
        nguyên nhân: {{ detector.cause }}
      </div>
      <div v-if="detector.unmatched.length" class="det-sub warn">
        không khớp topology: {{ detector.unmatched.join(', ') }}
      </div>
      <div v-if="detector.unattributed" class="det-sub">
        {{ detector.unattributed }} vi phạm tổng hợp không quy được về thiết bị
      </div>
    </div>

    <div class="control" :class="control.severity || 'ok'"
         :data-control-freshness="control.stale ? 'stale' : 'fresh'"
         :data-control-mode="control.mode">
      <div class="det-line">
        <span class="sev-dot"></span>
        <span class="who">Vòng kín</span>
        <span class="det-state">{{ control.modeLabel }}</span>
      </div>
      <div v-if="control.stale" class="det-sub">
        {{ control.lastConfirmedAgoMs === null
            ? 'chưa từng nhận nhịp tim của controller'
            : 'nhịp tim cuối ' + (control.lastConfirmedAgoMs / 1000).toFixed(1) + ' s trước' }}
      </div>
      <template v-else>
        <div class="det-sub">{{ control.modeDetail }}</div>
        <div v-if="control.mode === 'MITIGATING' && control.target" class="det-sub">
          🛡 {{ control.target }} giới hạn {{ control.limitMbps }} Mbps<span
            v-if="control.holdRemainingS !== null">, probe sau
            {{ Math.ceil(control.holdRemainingS) }} s</span>
        </div>
        <div v-else-if="control.mode === 'PROBING' && control.probeRemainingS !== null"
             class="det-sub">
          đang thăm dò, còn {{ Math.ceil(control.probeRemainingS) }} s
        </div>
      </template>
    </div>

    <div v-if="observability" class="observability" :class="observability.level">
      <span class="sev-dot"></span>
      <span class="who">{{ observability.label }}</span>
      <span class="what">{{ observability.detail }}</span>
    </div>

    <div v-if="clear" class="all-good">
      <span class="ok-dot"></span> All systems normal
    </div>

    <div v-else-if="alerts.length === 0" class="no-device-alert">
      Thiết bị: không có cảnh báo ngưỡng
    </div>

    <ul v-else class="alert-list">
      <li v-for="a in alerts" :key="a.key" :class="a.severity" @click="$emit('focus', a)">
        <span class="sev-dot"></span>
        <span class="who">{{ a.label }}</span>
        <span class="what">{{ a.reason }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { allClear, observabilityNote } from '../lib/controlView.js'

// DERIVED STATE (Lesson 3.4): KHÔNG lưu danh sách cảnh báo riêng. Tính TRỰC TIẾP
// từ graph mỗi khi graph đổi -> KHÔNG BAO GIỜ lệch với topology (single source).
// "derive, don't duplicate": nếu lưu riêng, alert có thể mâu thuẫn topology.
const props = defineProps(['graph', 'detector', 'control'])
defineEmits(['focus'])

const SEV = { critical: 3, warning: 2 }   // chỉ liệt kê những mức này

const alerts = computed(() => {
  const out = []

  for (const n of props.graph.nodes) {
    const sev = severityOf(n)
    if (sev) out.push({
      key: 'n:' + n.id, kind: 'node', id: n.id,
      label: `${n.type} ${n.id}`, severity: sev,
      reason: n.state === 'down' ? 'device down' : `${sev}`,
    })
  }
  for (const e of props.graph.edges) {
    const sev = severityOf(e)
    if (sev) out.push({
      key: 'e:' + e.id, kind: 'edge', id: e.id,
      label: `link ${e.from}–${e.to}`, severity: sev,
      reason: e.state === 'down' ? 'link down' : `${sev}`,
    })
  }
  // Sắp xếp: critical trước warning (nghiêm trọng lên đầu).
  return out.sort((a, b) => SEV[b.severity] - SEV[a.severity])
})

function severityOf(item) {
  if (item.state === 'down' || item.health === 'critical') return 'critical'
  if (item.health === 'warning') return 'warning'
  return null                              // ok/unknown -> không phải cảnh báo
}

// 8.5: all-clear KHÔNG còn chỉ nhìn detector. `normal` trong lúc controller
// đang MITIGATING là sự khoẻ mạnh DO CHÍNH NÓ tạo ra (bài học 8.2).
const clear = computed(() => allClear(alerts.value.length, props.detector, props.control))
const observability = computed(() => observabilityNote(props.detector))

// Badge đếm đổi màu theo mức nặng nhất đang có.
const worstClass = computed(() => {
  const detectorSeverity = props.detector?.severity
  const controlSeverity = props.control?.severity
  if (detectorSeverity === 'critical' || alerts.value.some(a => a.severity === 'critical')) return 'critical'
  if (detectorSeverity === 'warning' || controlSeverity === 'warning'
      || controlSeverity === 'stale' || alerts.value.some(a => a.severity === 'warning')) return 'warning'
  if (!clear.value) return 'unknown'
  return 'ok'
})
</script>

<style scoped>
.alert-panel { padding: 1rem 1.25rem; border-bottom: 1px solid #334155; }
h3 { color: #00F7F7; text-transform: uppercase; letter-spacing: 1px; font-size: 0.9rem;
  display: flex; align-items: center; gap: 8px; text-shadow: 0 0 8px rgba(0,247,247,0.4); }
.count { font-size: 0.75rem; padding: 1px 8px; border-radius: 10px; font-weight: 700; }
.count.ok { background: #14532d; color: #86efac; }
.count.warning { background: #7c4a03; color: #fdba74; }
.count.critical { background: #5a1d1d; color: #fca5a5; }
.count.unknown { background: #334155; color: #cbd5e1; }
.detector { border: 1px solid #334155; border-radius: 6px; padding: 6px 8px; margin: 0.5rem 0; font-size: 0.82rem; }
.det-line { display: flex; align-items: center; gap: 8px; }
.det-state { margin-left: auto; font-weight: 700; color: #e2e8f0; }
.det-sub { color: #94a3b8; font-size: 0.75rem; margin-top: 3px; }
.det-sub.warn { color: #fdba74; }
.detector .sev-dot { width: 9px; height: 9px; border-radius: 50%; background: #22c55e; }
.detector.stale { border-color: #a855f7; }
.detector.stale .sev-dot { background: #a855f7; box-shadow: 0 0 6px #a855f7; }
.detector.unknown .sev-dot { background: #64748b; }
.detector.warning .sev-dot { background: #f97316; }
.detector.critical .sev-dot { background: #F60000; box-shadow: 0 0 6px #F60000; }
.control { border: 1px solid #334155; border-radius: 6px; padding: 6px 8px; margin: 0.5rem 0; font-size: 0.82rem; }
.control .sev-dot { width: 9px; height: 9px; border-radius: 50%; background: #22c55e; }
.control.active { border-color: #38bdf8; }
.control.active .sev-dot { background: #38bdf8; box-shadow: 0 0 6px #38bdf8; }
.control.warning { border-color: #f97316; }
.control.warning .sev-dot { background: #f97316; }
.control.stale { border-color: #a855f7; }
.control.stale .sev-dot { background: #a855f7; box-shadow: 0 0 6px #a855f7; }
.control.unknown .sev-dot { background: #64748b; }
.observability { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  border: 1px dashed #f59e0b; border-radius: 6px; padding: 5px 8px; margin: 0.5rem 0;
  font-size: 0.78rem; color: #fcd34d; }
.observability .sev-dot { width: 9px; height: 9px; border-radius: 50%; background: #f59e0b; }
.observability .what { color: #94a3b8; }
.no-device-alert { color: #94a3b8; font-size: 0.8rem; padding: 4px 0; }
.all-good { color: #86efac; font-size: 0.85rem; display: flex; align-items: center; gap: 8px; padding: 6px 0; }
.ok-dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; }
.alert-list { list-style: none; margin: 0.5rem 0 0; padding: 0; max-height: 200px; overflow-y: auto; }
.alert-list li { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px;
  cursor: pointer; font-size: 0.82rem; margin-bottom: 3px; }
.alert-list li:hover { background: #0f172a; }
.sev-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.alert-list li.critical .sev-dot { background: #F60000; box-shadow: 0 0 6px #F60000; }
.alert-list li.warning .sev-dot { background: #f97316; }
.who { color: #e2e8f0; font-weight: 600; }
.what { color: #64748b; margin-left: auto; font-size: 0.75rem; }
</style>
