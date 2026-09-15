// ---------------------------------------------------------------------------
// sseClient.js — TẦNG DỊCH VỤ nghe thay đổi real-time từ Ditto qua SSE.
// Khâu NHẬN (Vấn đề 1, Lesson 3.3). Song song với dittoClient.js (fetch).
//
// TRÁCH NHIỆM DUY NHẤT: mở/đóng kết nối SSE, nhận event thô, gọi callback.
//   KHÔNG biết gì về merge/vẽ -> việc đó là của App.vue + translate.js.
//
// Vì sao EventSource (không phải fetch): SSE cần kết nối SỐNG LÂU + browser tự
//   reconnect khi rớt. EventSource làm sẵn cả hai -> đúng bản chất SSE (3.1).
// ---------------------------------------------------------------------------

const NAMESPACE = import.meta.env.VITE_DITTO_NAMESPACE || 'org.dt4n'

// Dùng đường proxy RIÊNG cho SSE ('/ditto-sse' — đã tắt buffer + không timeout
// trong vite.config.js). thingId LUÔN nằm trong fields, nếu không sẽ không biết
// event thuộc Thing nào (tài liệu Ditto nhấn mạnh điều này).
const SSE_PATH = `/ditto-sse/api/2/things?namespaces=${NAMESPACE}`
                 + `&fields=thingId,attributes,features`

// Mở stream. Trả về hàm close() để dừng nghe.
//   onDelta(thingJsonPartial): gọi mỗi khi có Thing-mảnh thay đổi.
//   onOpen():   gọi khi kết nối (lại) thành công -> App dùng để RE-SYNC.
//   onError():  gọi khi lỗi (EventSource sẽ tự thử lại sau đó).
export function openThingStream({ onDelta, onOpen, onError }) {
  const source = new EventSource(SSE_PATH)

  // Kết nối mở thành công (kể cả sau khi tự reconnect).
  source.onopen = () => { onOpen && onOpen() }

  // Mỗi event = một Thing JSON bị cắt gọt (chỉ nhánh thay đổi).
  source.onmessage = (event) => {
    // Ditto đôi khi gửi comment/heartbeat rỗng để giữ kết nối -> bỏ qua.
    if (!event.data || !event.data.trim()) return
    try {
      const partial = JSON.parse(event.data)
      onDelta && onDelta(partial)
    } catch (e) {
      // JSON hỏng -> bỏ qua 1 event, KHÔNG làm sập stream (defensive).
      console.warn('SSE: bỏ qua event không parse được', e)
    }
  }

  // Lỗi kết nối. EventSource TỰ ĐỘNG thử lại -> ta chỉ báo cho App biết.
  source.onerror = () => { onError && onError() }

  // Cho phép App chủ động đóng (khi rời trang / cleanup).
  return () => source.close()
}