import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createFreshness, observeFreshness, isStale } from '../src/lib/freshness.js'

const vectors = JSON.parse(readFileSync(
  new URL('../../test/fixtures/freshness_vectors.json', import.meta.url),
))

for (const testCase of vectors.cases) {
  test(`vector ${testCase.name}`, () => {
    const tracker = createFreshness()
    for (const step of testCase.steps) {
      if (step.observe) {
        const [bootId, seq] = step.observe
        assert.equal(
          observeFreshness(tracker, { bootId, seq }, step.at),
          step.accepted,
          `${testCase.name}@${step.at}`,
        )
      } else {
        assert.equal(
          isStale(tracker, vectors.ttl, step.at),
          step.stale,
          `${testCase.name}@${step.at}`,
        )
      }
    }
  })
}
