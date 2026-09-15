<template>
  <div class="topology-view">
    <h3>NETWORK TOPOLOGY</h3>
    <div class="diagram-container" ref="networkContainer"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { Network, DataSet } from 'vis-network/standalone'
import 'vis-network/styles/vis-network.css'

// props.graph = { nodes: [...], edges: [...] } ĐÃ được translate.js dịch sẵn.
// TopologyView KHÔNG còn đoán loại / parse label -> chỉ lo VẼ (Separation of Concerns).
const props = defineProps(['graph'])
const emit = defineEmits(['node-selected', 'edge-selected', 'selection-cleared'])

const networkContainer = ref(null)
const networkInstance = ref(null)
// DataSet giữ node/edge — vis-network tự vẽ lại khi DataSet đổi. Dùng DataSet
// (thay vì mảng thô) để setData cập nhật ĐÁNG TIN CẬY, tránh quirk của .update().
const nodesDS = new DataSet([])
const edgesDS = new DataSet([])

// Trigger cập nhật khi dữ liệu đổi (so sánh bằng chuỗi hóa).
const graphKey = computed(() => JSON.stringify(props.graph))

// --- Dịch node (đã có type/state) -> định dạng vis-network + màu theo trạng thái ---
function toVisNodes(nodes) {
  if (!Array.isArray(nodes)) return []
  return nodes.map(n => {
    // Chọn 'group' (kiểu tô màu) theo type + HEALTH (do twin tính sẵn).
    // KHÔNG tự suy trạng thái ở frontend -> health là single source of truth.
    let group = n.type                       // 'host' | 'switch' (mặc định = ok)
    if (n.state === 'down' || n.health === 'critical') group = `${n.type}-offline`
    else if (n.health === 'warning') group = `${n.type}-high-load`

    return {
      id: n.id,
      label: n.id,
      group,
      title: `${n.id}\nType: ${n.type}\nStatus: ${n.state}`,  // tooltip hover
    }
  })
}

// --- Dịch edge (đã có state) -> định dạng vis-network + màu/độ dày theo trạng thái ---
function toVisEdges(edges) {
  if (!Array.isArray(edges)) return []
  return edges.map(e => {
    // Đổi màu theo HEALTH (do twin tính, Lựa chọn B) — KHÔNG dùng e.state, vì
    // state chỉ có up/down/unknown, không bao giờ = 'warning'/'high-load'.
    // (Đây là lỗi cũ: nhánh warning/high-load chết vì nhìn nhầm trường.)
    let color = '#00F7F7', width = 2.5, dashes = false
    if (e.state === 'down' || e.health === 'critical') { color = '#F60000'; width = 4; dashes = (e.state === 'down') }
    else if (e.health === 'warning') { color = '#f97316'; width = 3.5 }

    return {
      id: e.id,
      from: e.from,
      to: e.to,
      color: { color, highlight: color, hover: color },
      width,
      dashes,
      smooth: { type: 'continuous', roundness: 0.5 },
      font: { color: '#00F7F7', size: 11, strokeWidth: 3, strokeColor: '#0f172a' },
    }
  })
}

// --- Cấu hình vis-network: GIỮ NGUYÊN phần đẹp từ repo cũ (màu neon, physics, icon) ---
const options = {
  physics: {
    enabled: true,
    stabilization: { iterations: 200 },
    solver: 'barnesHut',
    barnesHut: { gravitationalConstant: -12000, centralGravity: 0.08,
                 springLength: 120, springConstant: 0.06, damping: 0.12 },
  },
  interaction: { hover: true, tooltipDelay: 200, navigationButtons: false,
                 keyboard: false, selectConnectedEdges: false },
  nodes: {
    font: { color: '#00F7F7', size: 13, strokeWidth: 3, strokeColor: '#0f172a' },
    borderWidth: 3, size: 32, shape: 'dot',
  },
  edges: { color: { highlight: '#FFFFFF' }, selectionWidth: 4 },
  groups: {
    host:                { color: { border: '#0ea5e9', background: '#0f172a' },
                           shadow: { enabled: true, color: 'rgba(14,165,233,0.8)', size: 25 } },
    'host-offline':      { color: { border: '#475569', background: '#0f172a' },
                           borderDashes: [8, 8], shadow: { enabled: false } },
    'host-high-load':    { color: { border: '#F60000', background: '#0f172a' },
                           shadow: { enabled: true, color: 'rgba(246,0,0,0.8)', size: 25 } },
    switch:              { color: { border: '#f97316', background: '#0f172a' },
                           shadow: { enabled: true, color: 'rgba(249,115,22,0.8)', size: 25 } },
    'switch-offline':    { color: { border: '#475569', background: '#0f172a' },
                           borderDashes: [8, 8], shadow: { enabled: false } },
    'switch-high-load':  { color: { border: '#F60000', background: '#0f172a' },
                           shadow: { enabled: true, color: 'rgba(246,0,0,0.8)', size: 25 } },
  },
}

function buildData() {
  return { nodes: toVisNodes(props.graph?.nodes), edges: toVisEdges(props.graph?.edges) }
}

function syncDataSets() {
  const data = buildData()
  // setData(mảng mới) trên DataSet: thêm cái mới, sửa cái đổi, XOÁ cái không còn
  // -> đồ thị LUÔN khớp state. Đây là chỗ sửa lỗi "F5 mới thấy": trước dùng
  // .update() (không xoá, không luôn redraw) nên đồ thị lệch state tới khi F5.
  nodesDS.update(data.nodes)
  edgesDS.update(data.edges)
  // Xoá phần tử không còn trong graph mới (update không tự xoá).
  const keepN = new Set(data.nodes.map(n => n.id))
  const keepE = new Set(data.edges.map(e => e.id))
  nodesDS.getIds().forEach(id => { if (!keepN.has(id)) nodesDS.remove(id) })
  edgesDS.getIds().forEach(id => { if (!keepE.has(id)) edgesDS.remove(id) })
}

function initNetwork() {
  if (!networkContainer.value || !props.graph) return
  syncDataSets()
  networkInstance.value = new Network(networkContainer.value,
                                      { nodes: nodesDS, edges: edgesDS }, options)

  networkInstance.value.on('selectNode', p => {
    if (p.nodes.length) emit('node-selected', p.nodes[0])
  })
  networkInstance.value.on('selectEdge', p => {
    if (p.edges.length) emit('edge-selected', p.edges[0])
  })
  networkInstance.value.on('click', p => {
    if (!p.nodes.length && !p.edges.length) emit('selection-cleared')
  })
}

onMounted(initNetwork)

// Khi dữ liệu đổi (delta SSE về) -> đồng bộ DataSet -> vis-network TỰ vẽ lại.
// Không phải F5 nữa: DataSet là "nguồn" mà Network theo dõi trực tiếp.
watch(graphKey, () => {
  if (!networkInstance.value) return
  syncDataSets()
})
</script>

<style scoped>
.topology-view { min-width: 0; min-height: 0; padding: 1.5rem; background-color: #0f172a;
                 color: #94a3b8; display: flex; flex-direction: column; overflow: hidden; }
h3 { color: #00F7F7; margin-bottom: 1rem; text-transform: uppercase;
     letter-spacing: 1.2px; font-weight: 700; text-shadow: 0 0 10px rgba(0,247,247,0.5); }
.diagram-container { flex: 1; min-height: 0; border: 1px solid #334155; border-radius: 12px;
     background-color: #0f172a; overflow: hidden;
     border-bottom: 3px solid #00F7F7; box-shadow: 0 6px 20px rgba(0,247,247,0.3); }
:deep(.vis-navigation) { display: none !important; }
</style>
