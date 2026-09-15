// ---------------------------------------------------------------------------
// translate.js — LỚP DỊCH (Anti-Corruption Layer) phía frontend.
// Khâu TRANSLATE trong pipeline Lesson 3.2. LỚP 4 (frontend), phần "dịch".
//
// TRÁCH NHIỆM DUY NHẤT: biến Thing (ngôn ngữ Ditto) -> node/edge (ngôn ngữ
//   vis-network). KHÔNG gọi mạng, KHÔNG đụng DOM -> đây là các PURE FUNCTION
//   (cùng input luôn cho cùng output) => test được không cần browser.
//
// SỬA LỖI REPO CŨ: repo cũ đoán loại qua tên (id.startsWith('h')) -> 'srv1'
//   bị tưởng là switch. Ở đây ta ĐỌC attributes.type mà backend đã lưu tường
//   minh -> "đừng suy diễn cái phải được khai báo".
// ---------------------------------------------------------------------------


// ===========================================================================
// Việc 1: tách TÊN NGẮN từ thingId đầy đủ.
//   'org.dt4n:host-h1'    -> 'h1'
//   'org.dt4n:switch-s1'  -> 's1'
//   'org.dt4n:link-h1-s1' -> 'h1-s1'  (link không dùng làm node id, nhưng để đồng nhất)
// Lấy phần sau dấu ':' rồi bỏ tiền tố loại ('host-'/'switch-'/'link-').
// ===========================================================================
export function shortName(thingId) {
  const afterColon = thingId.split(':').pop()          // 'host-h1'
  return afterColon.replace(/^(host|switch|link)-/, '') // 'h1'
}


// ===========================================================================
// Đọc một property lồng sâu an toàn: features.<feature>.properties.<key>.
// Ditto lồng 'properties' (nhớ adapter.py). Dùng ?. để KHÔNG vỡ nếu thiếu tầng.
// ===========================================================================
function prop(thing, feature, key) {
  return thing?.features?.[feature]?.properties?.[key]
}


// ===========================================================================
// Việc 2 + 3: dịch danh sách Thing -> { nodes: [...], edges: [...] }.
// Đây là HÀM CHÍNH mà component gọi.
// ===========================================================================
export function thingsToGraph(things) {
  const nodes = []
  const edges = []

  for (const thing of things) {
    // NGUỒN SỰ THẬT về loại: attributes.type (KHÔNG đoán qua tên).
    const type = thing?.attributes?.type
    const name = shortName(thing.thingId)

    if (type === 'host' || type === 'switch') {
      // --- HOST / SWITCH -> NODE ---
      // Lesson 3.4 (Lựa chọn B): ĐỌC healthState do TWIN tính sẵn, KHÔNG tự tính.
      // health là single source of truth -> dashboard/ML/controller cùng 1 trạng thái.
      const state = prop(thing, 'status', 'state') || 'unknown'
      const health = prop(thing, 'health', 'state') || 'unknown'

      nodes.push({
        id: name,                 // tên ngắn -> khớp endpointA/B của link
        label: name,
        rawId: thing.thingId,
        type,                     // giữ để chọn icon/màu ở tầng vẽ
        state,                    // 'up' | 'down' | ... (trạng thái vật lý)
        health,                   // 'ok'|'warning'|'critical'|'unknown' (do twin tính)
        raw: thing,
      })
    } else if (type === 'link') {
      // --- LINK -> EDGE --- (đọc 2 đầu đã lưu sẵn ở Phase 2)
      const a = thing?.attributes?.endpointA
      const b = thing?.attributes?.endpointB
      if (!a || !b) continue      // thiếu 2 đầu -> bỏ qua an toàn, không vẽ cạnh mồ côi

      edges.push({
        id: name,                 // 'h1-s1'
        rawId: thing.thingId,
        from: a,
        to: b,
        state: prop(thing, 'status', 'state') || 'unknown',
        health: prop(thing, 'health', 'state') || 'unknown',
        bwMbps: prop(thing, 'capacity', 'bwMbps') ?? null,
        raw: thing,
      })
    }
    // type lạ / thiếu -> lặng lẽ bỏ qua (defensive: không cho dữ liệu rác làm vỡ đồ thị)
  }

  return { nodes, edges }
}


// ===========================================================================
// LESSON 3.3 — DEEP MERGE cho real-time.
//
// SSE endpoint /api/2/things trả về Thing JSON BỊ CẮT GỌT (chỉ nhánh thay đổi,
// nhưng GIỮ cấu trúc lồng). Ví dụ đổi rxRate:
//   { thingId: "org.dt4n:host-h1",
//     features: { traffic: { properties: { rxRate: 2048 } } } }
// -> ta chỉ cần merge SÂU cái mảnh này vào Thing đầy đủ trong state.
// (KHÁC với Ditto Protocol dạng {path,value} của WebSocket — SSE là Thing JSON.)
// ===========================================================================

// Deep merge: trộn 'patch' vào 'target' tới tận field lá.
//   - Nếu cả hai cùng là object -> đệ quy xuống sâu (KHÔNG thay nguyên nhánh).
//   - Ngược lại -> patch ghi đè.
// Đây là chỗ tránh lỗi "shallow merge xóa mất field anh em" ở lý thuyết 3.3.
export function deepMerge(target, patch) {
  if (!isPlainObject(target) || !isPlainObject(patch)) return patch
  const out = { ...target }
  for (const key of Object.keys(patch)) {
    out[key] = deepMerge(target[key], patch[key])   // đệ quy -> merge sâu
  }
  return out
}

function isPlainObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

// Áp một Thing-mảnh (từ SSE) vào 'thingsById' (map thingId -> Thing đầy đủ).
// Trả về map MỚI (immutable -> Vue phát hiện thay đổi, dễ debug, không side-effect).
// Xử lý đủ 3 loại: CREATE (Thing mới), UPDATE (merge sâu), DELETE (báo hiệu xóa).
export function applyDelta(thingsById, delta) {
  const id = delta?.thingId
  if (!id) return thingsById                         // không có thingId -> bỏ (defensive)

  const next = { ...thingsById }

  // Ditto báo xóa bằng field _deleted (hoặc không còn attributes/features).
  if (delta.__deleted === true) {
    delete next[id]                                  // DELETE
    return next
  }

  const existing = next[id]
  next[id] = existing ? deepMerge(existing, delta)   // UPDATE (merge sâu)
                      : delta                          // CREATE (Thing mới toanh)
  return next
}
