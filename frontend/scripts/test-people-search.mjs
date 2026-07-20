import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const componentUrl = new URL('../src/components/NSearch.vue', import.meta.url)
const composableUrl = new URL('../src/composables/usePeopleSearch.ts', import.meta.url)
const peopleStoreUrl = new URL('../src/stores/organizationPeople.ts', import.meta.url)
const peopleViewUrl = new URL('../src/views/orgs/People.vue', import.meta.url)

test('NSearch delegates lookup to a server-paginated search controller', async () => {
  const component = await readFile(componentUrl, 'utf8')

  assert.match(component, /usePeopleSearch/)
  assert.match(component, /search\.hasMore\.value/)
  assert.match(component, /keepDropdownOpen\(search\.loadMore\)/)
  assert.match(component, /inputRef\.value\?\.focus\(\)/)
  assert.match(component, /Show more results/)
  assert.doesNotMatch(component, /findMostSimilarWord|\blist\??:/)
})

test('people search controller cancels stale requests and appends ranked pages', async () => {
  const composable = await readFile(composableUrl, 'utf8')

  assert.match(composable, /new AbortController\(\)/)
  assert.match(composable, /requestController\?\.abort\(\)/)
  assert.match(composable, /context\.id == this\.requestId/)
  assert.match(composable, /this\.searchPage\(this\.page \+ 1, true\)/)
  assert.match(composable, /append \? \[\.\.\.this\.people\.value/)
  assert.match(composable, /onBeforeUnmount\(\(\) => controller\.cancel\(\)\)/)
})

test('NSearch exposes bounded loading, empty, retry, and minimum-input states', async () => {
  const component = await readFile(componentUrl, 'utf8')

  assert.match(component, /Type at least 2 characters/)
  assert.match(component, /Searching people/)
  assert.match(component, /Loading more people/)
  assert.match(component, /No matching person found/)
  assert.match(component, /People search failed/)
  assert.match(component, /retry-search/)
})

test('people store keeps DRF page metadata and sends the requested page', async () => {
  const store = await readFile(peopleStoreUrl, 'utf8')

  assert.match(store, /searchPeople\([\s\S]*page = 1[\s\S]*signal\?: AbortSignal/)
  assert.match(store, /search, page, page_size: pageSize/)
  assert.match(store, /signal/)
  assert.match(store, /getPaginatedResults<IPerson>/)
  assert.match(store, /hasMore: Boolean\(metadata\?\.next\)/)
  assert.match(store, /requestId == state\.peopleRequestId/)
})

test('People directory applies NSearch queries to remote table pagination', async () => {
  const view = await readFile(peopleViewUrl, 'utf8')

  assert.match(view, /@search="handleDirectorySearch"/)
  assert.match(view, /:remote="true"/)
  assert.match(view, /search: directorySearch\.value/)
  assert.match(view, /currentPage\.value = 1/)
})
