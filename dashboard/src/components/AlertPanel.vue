<template>
  <div class="alert-panel">
    <h3>ALERTS <span class="count" :class="worstClass">{{ alerts.length }}</span></h3>

    <div v-if="alerts.length === 0" class="all-good">
      <span class="ok-dot"></span> All systems normal
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

// DERIVED STATE (Lesson 3.4): KHÔNG lưu danh sách cảnh báo riêng. Tính TRỰC TIẾP
// từ graph mỗi khi graph đổi -> KHÔNG BAO GIỜ lệch với topology (single source).
// "derive, don't duplicate": nếu lưu riêng, alert có thể mâu thuẫn topology.
const props = defineProps(['graph'])
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

// Badge đếm đổi màu theo mức nặng nhất đang có.
const worstClass = computed(() => {
  if (alerts.value.some(a => a.severity === 'critical')) return 'critical'
  if (alerts.value.some(a => a.severity === 'warning')) return 'warning'
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