import assert from 'node:assert/strict'
import test from 'node:test'
import { parseBooleanFeatureFlag } from '../src/services/featureFlags.ts'
import {
  getArrayFilterFunc,
  getBooleanFilterFunc,
  getDateFilterFunc,
  getStringFilterFunc
} from '../src/services/tableFilters.ts'

test('parses production feature flags without enabling the string false', () => {
  assert.equal(parseBooleanFeatureFlag('true'), true)
  assert.equal(parseBooleanFeatureFlag('false'), false)
  assert.equal(parseBooleanFeatureFlag('0'), false)
  assert.equal(parseBooleanFeatureFlag('unexpected', true), true)
})

test('matches equal dates and supports both accepted date formats', () => {
  const filter = getDateFilterFunc('date')
  assert.equal(filter({ date: '19.07.2026', type: '==' }, { date: '2026-07-19' }), true)
  assert.equal(filter({ date: '19.07.2026', type: '!=' }, { date: '2026-07-19' }), false)
})

test('compares dates and fails closed for malformed values', () => {
  const filter = getDateFilterFunc('date')
  assert.equal(filter({ date: '18.07.2026', type: '>' }, { date: '2026-07-19' }), true)
  assert.equal(filter({ date: '20.07.2026', type: '<' }, { date: '2026-07-19' }), true)
  assert.equal(filter({ date: 'not-a-date', type: '==' }, { date: '2026-07-19' }), false)
})

test('handles string, boolean, and array cells without unsafe assumptions', () => {
  assert.equal(getStringFilterFunc('number')('23', { number: 1234 }), true)
  assert.equal(getBooleanFilterFunc('active')(true, { active: true }), true)
  assert.equal(getArrayFilterFunc('status')(['open'], { status: ['draft', 'open'] }), true)
  assert.equal(getArrayFilterFunc('status')([], { status: null }), true)
})
