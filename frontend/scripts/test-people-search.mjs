import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const componentUrl = new URL('../src/components/NSearch.vue', import.meta.url)
const peopleStoreUrl = new URL('../src/stores/organizationPeople.ts', import.meta.url)

test('NSearch uses cancellable server search instead of a local people page', async () => {
  const component = await readFile(componentUrl, 'utf8')

  assert.match(component, /new AbortController\(\)/)
  assert.match(component, /activeController\?\.abort\(\)/)
  assert.match(component, /onBeforeUnmount\(cancelPendingSearch\)/)
  assert.match(component, /store\.searchPeople\(value, 10, controller\.signal\)/)
  assert.doesNotMatch(component, /findMostSimilarWord|\blist\??:/)
})

test('NSearch exposes bounded loading, empty, error, and minimum-input states', async () => {
  const component = await readFile(componentUrl, 'utf8')

  assert.match(component, /Type at least 2 characters/)
  assert.match(component, /Searching people/)
  assert.match(component, /No matching person found/)
  assert.match(component, /People search failed/)
  assert.match(component, /setTimeout\(\(\) => searchPeople\(value\), delay\)/)
})

test('people store sends the query, page size, and cancellation signal to DRF', async () => {
  const store = await readFile(peopleStoreUrl, 'utf8')

  assert.match(store, /searchPeople\([\s\S]*signal\?: AbortSignal/)
  assert.match(store, /search, page_size: pageSize/)
  assert.match(store, /signal/)
  assert.match(store, /getPaginatedResults<IPerson>/)
})
