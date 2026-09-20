import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { createFreshness, observeFreshness } from '../src/lib/freshness.js'
import { detectorView, severityOf, DETECTOR_SEVERITY } from '../src/lib/detectorView.js'
// allClear song o controlView.js tu 8.5 (doi ca controller). Cac test duoi day
// truyen mot controller SONG va IDLE de van do dung cai chung muon do: detector.
import { allClear as allClearBoth } from '../src/lib/controlView.js'
const LIVE_IDLE = { present: true, stale: false, mode: 'IDLE' }
const allClear = (n, view) => allClearBoth(n, view, LIVE_IDLE)

const GRAPH = {
  nodes: [{ id: 'h1' }, { id: 'srv1' }, { id: 's1' }],
  edges: [{ id: 'h1-s1' }, { id: 's1-s2' }],
}

function thing(state, evidence = {}, seq = 1, boot = 'a') {
  return { thingId: 'org.dt4n:detector', features: {
    decision: { properties: { state, cause: '', reason: 'r' } },
    evidence: { properties: {
      envelope: false, conservation: false, actRule: false,
      affected: [], unattributed: 0, ...evidence,
    } },
    freshness: { properties: {
      bootId: boot, seq, ttlTicks: 3, tickIntervalMs: 1000, dropped: 0,
    } },
  } }
}

function fresh() {
  const tracker = createFreshness()
  observeFreshness(tracker, { bootId: 'a', seq: 0 }, 0)
  observeFreshness(tracker, { bootId: 'a', seq: 1 }, 1000)
  return tracker
}

test('MAP: severity chỉ phụ thuộc state và stale, không phụ thuộc evidence', () => {
  const combinations = [
    {}, { envelope: true }, { conservation: true }, { actRule: true },
    { envelope: true, conservation: true, actRule: true },
  ]
  for (const state of Object.keys(DETECTOR_SEVERITY)) {
    const severities = new Set(combinations.map(evidence =>
      detectorView(thing(state, evidence), fresh(), 1500, GRAPH).severity))
    assert.equal(severities.size, 1, state)
    assert.equal([...severities][0], severityOf(state, false))
  }
})

test('suspect không có evidence vẫn là warning do hysteresis', () => {
  const view = detectorView(thing('suspect'), fresh(), 1500, GRAPH)
  assert.equal(view.severity, 'warning')
  assert.equal(view.channel, 'đang giữ trạng thái (hysteresis)')
})

test('nhãn phân biệt kênh nhanh và kênh chậm', () => {
  assert.match(detectorView(thing('act', { actRule: true }), fresh(), 1500, GRAPH).channel, /nhanh/)
  assert.match(detectorView(thing('suspect', { conservation: true }), fresh(), 1500, GRAPH).channel, /chậm/)
})

test('STALE không bao giờ là bình thường và mặc định khi tải trang là STALE', () => {
  const tracker = createFreshness()
  observeFreshness(tracker, { bootId: 'a', seq: 4812 }, 0)
  const view = detectorView(thing('normal', {}, 4812), tracker, 10, GRAPH)
  assert.equal(view.stale, true)
  assert.equal(view.severity, 'stale')
  assert.equal(allClear(0, view), false)
  assert.equal(allClear(0, detectorView(null, createFreshness(), 0, GRAPH)), false)
})

test('all clear chỉ khi thiết bị ổn và detector tươi, normal', () => {
  assert.equal(allClear(0, detectorView(thing('normal'), fresh(), 1500, GRAPH)), true)
  assert.equal(allClear(0, detectorView(thing('unknown'), fresh(), 1500, GRAPH)), false)
  assert.equal(allClear(1, detectorView(thing('normal'), fresh(), 1500, GRAPH)), false)
})

test('stale_intervention ở state normal không được là all clear', () => {
  const detector = thing('normal')
  detector.features.decision.properties.cause = 'stale_intervention'
  const view = detectorView(detector, fresh(), 1500, GRAPH)
  assert.equal(view.severity, null)
  assert.equal(allClear(0, view), false)
})

test('affected join theo id và báo id không khớp', () => {
  const view = detectorView(thing('act', {
    actRule: true,
    affected: ['org.dt4n:host-h1', 'org.dt4n:link-h1-s1', 'org.dt4n:link-h9-s9'],
    unattributed: 2,
  }), fresh(), 1500, GRAPH)
  assert.deepEqual(view.highlight, ['h1', 'h1-s1'])
  assert.deepEqual(view.unmatched, ['h9-s9'])
  assert.equal(view.unattributed, 2)
})

test('không highlight bằng chứng cũ khi STALE', () => {
  const view = detectorView(
    thing('act', { affected: ['org.dt4n:host-h1'] }),
    fresh(),
    9000,
    GRAPH,
  )
  assert.deepEqual(view.highlight, [])
})

test('state lạ không bao giờ biến thành normal', () => {
  assert.equal(severityOf('bogus', false), 'unknown')
})

test('FIREWALL: dashboard không chứa logic ngưỡng detector', () => {
  const files = []
  const walk = directory => readdirSync(directory, { withFileTypes: true }).forEach(entry =>
    entry.isDirectory()
      ? walk(`${directory}/${entry.name}`)
      : files.push(`${directory}/${entry.name}`))
  walk(new URL('../src', import.meta.url).pathname)
  const banned = [
    /8\.9688/, /0\.0796/, /4\.3126/, /\bexcess\b/, /r_max/, /k_rate/,
    /evidence[^\n]*(>|<)=?\s*\d/,
  ]
  for (const file of files) {
    const source = readFileSync(file, 'utf8')
    for (const pattern of banned) assert.ok(!pattern.test(source), `${file} chứa ${pattern}`)
  }
})
