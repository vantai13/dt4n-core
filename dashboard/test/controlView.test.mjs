// Phase 8.5: controlView là MAP thuần của (mode, stale). Test ở đây khoá
// đúng ba thứ: tính thuần, firewall "không suy từ hiện thực", và all-clear.
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { test } from 'node:test'

import { createFreshness, observeFreshness } from '../src/lib/freshness.js'
import {
  CONTROL_SEVERITY, allClear, controlSeverityOf, controlView, observabilityNote,
} from '../src/lib/controlView.js'

const MODES = ['IDLE', 'MITIGATING', 'PROBING', 'HOLD', 'LA_HOAC']
const det = (over = {}) => ({
  present: true, stale: false, state: 'normal', cause: '', ...over,
})

function controlThing({ mode = 'IDLE', target = '', limit = 0, hold = 0,
                        probe = 0, seq = 1, boot = 'ctl-1' } = {}) {
  return {
    thingId: 'org.dt4n:controlloop',
    features: {
      decision: { properties: { mode, target, limitMbps: limit, reason: 'x',
                                decidedAt: '' } },
      schedule: { properties: { holdRemainingS: hold, probeRemainingS: probe,
                                attempt: 0, episode: 1 } },
      freshness: { properties: { bootId: boot, seq, ttlTicks: 3,
                                 tickIntervalMs: 1000 } },
    },
  }
}

function armed(boot = 'ctl-1', atMs = 0) {
  // isStale trả true tới khi quan sát được một thay đổi hợp lệ -> arm hai nhịp.
  // `atMs` là lúc nhịp cuối tới: TTL đếm từ đó.
  const tr = createFreshness()
  observeFreshness(tr, { bootId: boot, seq: 1 }, atMs)
  observeFreshness(tr, { bootId: boot, seq: 2 }, atMs)
  return tr
}

// ---------------------------------------------------------------- firewall

test('controlView không suy diễn từ hiện thực (bwMbps/txRate)', () => {
  const src = readFileSync(new URL('../src/lib/controlView.js', import.meta.url), 'utf8')
  const code = src.split('\n').filter(l => !l.trim().startsWith('//')).join('\n')
  for (const cam of ['capacity', 'bwMbps', 'thingBw', 'txRate', 'features.traffic']) {
    assert.ok(!code.includes(cam),
      `controlView.js suy diễn từ "${cam}" -> nguồn sự thật thứ hai`)
  }
})

test('chỉ có MỘT allClear trong toàn dashboard', () => {
  // Ngu nghia doi -> KHONG de ban cu song song duoi cung mot ten. Hoac xoa,
  // hoac doi ten, de lap trinh vien phai chon CO Y THUC.
  // Doc bang fs, KHONG goi grep: test phai chay dung du cwd la dashboard/ hay
  // goc repo (test/test_phase7_freshness.py chay `node --test` tu goc repo).
  const libDir = new URL('../src/lib/', import.meta.url)
  const hits = readdirSync(libDir)
    .filter(name => name.endsWith('.js'))
    .filter(name => readFileSync(new URL(name, libDir), 'utf8')
      .includes('export function allClear'))
  assert.deepEqual(hits, ['controlView.js'])
})

// ---------------------------------------------------------------- thuần

test('nhãn vòng kín chỉ phụ thuộc (mode, stale)', () => {
  for (const mode of MODES) {
    for (const stale of [true, false]) {
      assert.equal(controlSeverityOf(mode, stale), controlSeverityOf(mode, stale))
      if (stale) assert.equal(controlSeverityOf(mode, stale), 'stale')
    }
  }
  assert.equal(controlSeverityOf('LA_HOAC', false), 'unknown')
  assert.equal(controlSeverityOf(undefined, false), 'unknown')
  assert.equal(CONTROL_SEVERITY.PROBING, 'active')
  assert.equal(CONTROL_SEVERITY.HOLD, 'warning')
})

test('thiếu mode -> HOLD, không phải IDLE', () => {
  const view = controlView({ thingId: 'x', features: {} }, armed(), 0)
  assert.equal(view.mode, 'HOLD')
  assert.notEqual(view.mode, 'IDLE')
})

test('không có Thing -> stale và không present', () => {
  const view = controlView(null, createFreshness(), 0)
  assert.equal(view.present, false)
  assert.equal(view.stale, true)
  assert.equal(view.severity, 'stale')
  assert.equal(view.holdRemainingS, null)
})

// ---------------------------------------------------------------- đếm ngược

test('đếm ngược từ KHOẢNG, neo vào lúc nhận, kẹp sàn 0', () => {
  const thing = controlThing({ mode: 'MITIGATING', target: 'h1', hold: 30 })
  // nhịp tới lúc 1000 ms: ngay lúc nhận thì còn nguyên 30 s
  assert.equal(controlView(thing, armed('ctl-1', 1000), 1000, 1000).holdRemainingS, 30)
  // 2,5 s sau (vẫn trong TTL 3 s): đếm bằng đồng hồ của chính trình duyệt
  assert.equal(controlView(thing, armed('ctl-1', 3500), 3500, 1000).holdRemainingS, 27.5)
  // nhịp vẫn đều nhưng bản tin cũ đã hết giờ -> KẸP SÀN 0, không âm
  assert.equal(controlView(thing, armed('ctl-1', 99000), 99000, 1000).holdRemainingS, 0)
})

test('STALE thì NGỪNG đếm ngược', () => {
  const tr = armed()
  const thing = controlThing({ mode: 'MITIGATING', target: 'h1', hold: 30 })
  const view = controlView(thing, tr, 10000, 0)     // ttl 3 s -> stale
  assert.equal(view.stale, true)
  assert.equal(view.holdRemainingS, null)
  assert.equal(view.probeRemainingS, null)
})

// ---------------------------------------------------------------- all-clear

test('không all-clear khi controller không IDLE', () => {
  for (const mode of ['MITIGATING', 'PROBING', 'HOLD']) {
    assert.equal(allClear(0, det(), { present: true, stale: false, mode }), false)
  }
  assert.equal(allClear(0, det(), { present: true, stale: false, mode: 'IDLE' }), true)
})

test('detector sống KHÔNG che được controller chết (masking)', () => {
  assert.equal(allClear(0, det(), { present: true, stale: true, mode: 'IDLE' }), false)
  assert.equal(allClear(0, det(), { present: false, stale: true, mode: 'HOLD' }), false)
  assert.equal(allClear(0, det(), null), false)
})

test('all-clear vẫn tôn trọng mọi điều kiện của Phase 7', () => {
  const ok = { present: true, stale: false, mode: 'IDLE' }
  assert.equal(allClear(1, det(), ok), false)                       // có cảnh báo thiết bị
  assert.equal(allClear(0, det({ stale: true }), ok), false)
  assert.equal(allClear(0, det({ state: 'act' }), ok), false)
  assert.equal(allClear(0, det({ cause: 'missing_data' }), ok), false)
})

// ---------------------------------------------------------------- kênh 🛡

test('shielded chỉ khi MITIGATING và không stale', () => {
  const tr = armed()
  const mit = controlThing({ mode: 'MITIGATING', target: 'h1', limit: 7 })
  assert.deepEqual(controlView(mit, tr, 0, 0).shielded, ['h1', 'h1-s1'])
  const probing = controlThing({ mode: 'PROBING', target: 'h1' })
  assert.deepEqual(controlView(probing, tr, 0, 0).shielded, [])
  assert.deepEqual(controlView(mit, tr, 99000, 0).shielded, [])      // stale
})

// ---------------------------------------------------------------- quan sát

test('nhãn quan sát bị thu hẹp là MAP từ cause, không suy diễn', () => {
  assert.equal(observabilityNote(det()), null)
  assert.equal(observabilityNote(det({ cause: 'missing_data' })), null)
  const note = observabilityNote(det({ state: 'unknown',
                                       cause: 'suppressed_intervention' }))
  assert.equal(note.level, 'caution')
  assert.ok(note.label.includes('THU HẸP'))
  assert.ok(!note.detail.includes('mù'))            // 1/3 round không bị ức chế (8.3)
  assert.equal(observabilityNote(det({ stale: true,
                                       cause: 'suppressed_intervention' })), null)
})

// ---------------------------------------------------------------- freshness

test('hai tracker độc lập, bootId không lẫn sang nhau', () => {
  const d = createFreshness()
  const c = createFreshness()
  observeFreshness(d, { bootId: 'det-1', seq: 1 }, 0)
  observeFreshness(c, { bootId: 'ctl-1', seq: 1 }, 0)
  observeFreshness(d, { bootId: 'det-2', seq: 0 }, 1000)     // detector restart
  assert.equal(observeFreshness(c, { bootId: 'ctl-1', seq: 2 }, 1100), true)
  assert.equal(c.retired.size, 0)
  assert.equal(d.retired.size, 1)
})
