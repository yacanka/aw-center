import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const pagePaths = [
  '../src/views/MediaConverter.vue',
  '../src/views/Translator.vue',
  '../src/views/compdoc/DocAnalyzer.vue',
  '../src/views/compdoc/CoverPageCreator.vue'
]

test('worker-backed pages monitor jobs without forced navigation', async () => {
  const sources = await Promise.all(
    pagePaths.map((path) => readFile(new URL(path, import.meta.url), 'utf8'))
  )

  for (const source of sources) {
    assert.match(source, /PageJobStatus/)
    assert.match(source, /usePageJob\(/)
    assert.match(source, /setJob\(await create/)
    assert.doesNotMatch(source, /router\.push\(['"]\/jobs['"]\)/)
  }
})

test('page job monitor restores, polls, cancels, retries, and opens Job Center', async () => {
  const source = await readFile(
    new URL('../src/composables/usePageJob.ts', import.meta.url),
    'utf8'
  )

  assert.match(source, /this\.route\.query\[this\.queryKey\]/)
  assert.match(source, /window\.setTimeout\(this\.refresh/)
  assert.match(source, /onBeforeUnmount\(monitor\.stopRefresh\)/)
  assert.match(source, /cancelJob\(/)
  assert.match(source, /retryJob\(/)
  assert.match(source, /downloadJob\(/)
  assert.match(source, /name: 'jobs', query: \{ job:/)
})

test('inline status surfaces progress, cancellation, and explicit Job Center navigation', async () => {
  const [statusCard, dccStatus, dccCreator] = await Promise.all([
    readFile(new URL('../src/components/jobs/PageJobStatus.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/dcc/DccJobStatus.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/dcc/DCCCreator.vue', import.meta.url), 'utf8')
  ])

  assert.match(statusCard, /job\.progress/)
  assert.match(statusCard, /job\.message/)
  assert.match(statusCard, /job\.can_cancel/)
  assert.match(statusCard, /Show in Job Center/)
  assert.match(dccStatus, /job\.can_cancel/)
  assert.match(dccCreator, /cancelCurrentJob/)
  assert.match(dccCreator, /cancelJob\(currentJob\.value\.id\)/)
})
