<template>
  <div class="hist-overlay" @click.self="$emit('close')">
    <div class="hist-drawer">
      <div class="hist-head">
        <h3>LỊCH SỬ THAY ĐỔI</h3>
        <div class="hist-actions">
          <button class="hist-btn" @click="load" title="Làm mới">↻</button>
          <button class="hist-btn" @click="$emit('close')" title="Đóng">✕</button>
        </div>
      </div>

      <div v-if="loading" class="hist-empty">Đang tải...</div>
      <div v-else-if="entries.length === 0" class="hist-empty">Chưa có thay đổi nào.</div>
      <ul v-else class="hist-list">
        <li v-for="(e, i) in entries" :key="i" :class="resultClass(e.result)">
          <span class="hist-ts">{{ fmtTs(e.ts) }}</span>
          <span class="hist-act">{{ e.subject }}</span>
          <span class="hist-tgt">{{ shortTarget(e.target) }}</span>
          <span class="hist-res" :class="resultClass(e.result)">{{ e.result }}</span>
          <span v-if="e.reason" class="hist-reason">{{ e.reason }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

defineEmits(['close'])

const entries = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await fetch('/_dt4n/history')
    const data = await res.json()
    entries.value = data.entries || []
  } catch (_) {
    entries.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)

function fmtTs(ts) {
  if (!ts) return '-'
  const d = new Date(ts)
  return isNaN(d.getTime()) ? ts : d.toLocaleString()
}

function shortTarget(t) {
  return t ? String(t).split(':').pop() : '-'
}

function resultClass(r) {
  if (r === 'ok') return 'ok'
  if (r === 'rejected' || r === 'error') return 'bad'
  if (r === 'duplicate_ignored') return 'dup'
  return ''
}
</script>

<style scoped>
.hist-overlay { position: fixed; inset: 0; background: rgba(2,6,23,0.6);
  display: flex; justify-content: flex-end; z-index: 50; }
.hist-drawer { width: 460px; max-width: 92vw; height: 100%; background: #0f172a;
  border-left: 1px solid #334155; display: flex; flex-direction: column;
  box-shadow: -8px 0 24px rgba(0,0,0,0.4); }
.hist-head { display: flex; align-items: center; justify-content: space-between;
  gap: 1rem; padding: 1rem 1.25rem; border-bottom: 1px solid #334155; }
.hist-head h3 { margin: 0; color: #00F7F7; letter-spacing: 1px; font-size: 0.95rem;
  text-shadow: 0 0 8px rgba(0,247,247,0.4); }
.hist-actions { display: flex; gap: 8px; }
.hist-btn { background: #1e293b; color: #e2e8f0; border: 1px solid #334155;
  border-radius: 6px; width: 34px; height: 30px; cursor: pointer; font-weight: 700; }
.hist-btn:hover { filter: brightness(1.2); }
.hist-empty { color: #64748b; padding: 1.5rem; text-align: center; }
.hist-list { list-style: none; margin: 0; padding: 0.5rem; overflow-y: auto; }
.hist-list li { display: grid;
  grid-template-columns: minmax(0, 150px) minmax(90px, 110px) minmax(0, 1fr) auto;
  gap: 8px; align-items: center; padding: 8px 10px; border-radius: 6px;
  font-size: 0.82rem; color: #cbd5e1; border-left: 3px solid #334155;
  margin-bottom: 4px; background: #1e293b; }
.hist-list li.ok { border-left-color: #16a34a; }
.hist-list li.bad { border-left-color: #dc2626; }
.hist-list li.dup { border-left-color: #64748b; opacity: 0.75; }
.hist-list span { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.hist-ts { color: #64748b; font-variant-numeric: tabular-nums; white-space: nowrap; }
.hist-act { color: #00F7F7; font-weight: 700; }
.hist-tgt { color: #e2e8f0; }
.hist-res { justify-self: end; font-weight: 700; text-transform: uppercase; font-size: 0.72rem; }
.hist-res.ok { color: #86efac; }
.hist-res.bad { color: #fca5a5; }
.hist-reason { grid-column: 1 / -1; color: #94a3b8; font-style: italic;
  font-size: 0.78rem; white-space: normal; overflow-wrap: anywhere; }

@media (max-width: 520px) {
  .hist-list li { grid-template-columns: minmax(0, 1fr) auto; }
  .hist-ts, .hist-act, .hist-tgt { grid-column: 1 / 2; }
  .hist-res { grid-column: 2 / 3; grid-row: 1 / 2; }
}
</style>
