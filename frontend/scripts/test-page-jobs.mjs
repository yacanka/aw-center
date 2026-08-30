import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const pagePaths = [
  '../src/features/tools/pages/MediaConverter.vue',
  '../src/features/tools/pages/Translator.vue',
  '../src/features/compliance/pages/DocAnalyzer.vue',
  '../src/features/compliance/pages/CoverPageCreator.vue'
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

test('page job monitor restores, polls, cancels, downloads, and opens Job Center', async () => {
  const source = await readFile(
    new URL('../src/features/jobs/composables/usePageJob.ts', import.meta.url),
    'utf8'
  )

  assert.match(source, /this\.route\.query\[this\.queryKey\]/)
  assert.match(source, /window\.setTimeout\(this\.refresh/)
  assert.match(source, /onBeforeUnmount\(monitor\.stopRefresh\)/)
  assert.match(source, /cancelJob\(/)
  assert.doesNotMatch(source, /retryJob\(/)
  assert.match(source, /downloadJob\(/)
  assert.match(source, /name: 'jobs', query: \{ job:/)
})

test('inline status surfaces progress, cancellation, and explicit Job Center navigation', async () => {
  const [statusCard, dccStatus, dccCreator] = await Promise.all([
    readFile(new URL('../src/features/jobs/components/PageJobStatus.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/features/dcc/components/DccJobStatus.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/features/dcc/pages/DCCCreator.vue', import.meta.url), 'utf8')
  ])

  assert.match(statusCard, /job\.progress/)
  assert.match(statusCard, /job\.message/)
  assert.match(statusCard, /job\.can_cancel/)
  assert.match(statusCard, /Show in Job Center/)
  assert.match(dccStatus, /job\.can_cancel/)
  assert.match(dccCreator, /cancelCurrentJob/)
  assert.match(dccCreator, /cancelJob\(currentJob\.value\.id\)/)
})

test('presentation conversion uses durable jobs and refreshes owner-scoped gallery state', async () => {
  const [gallery, uploader, list, store] = await Promise.all([
    readFile(new URL('../src/features/tools/pages/Presentations.vue', import.meta.url), 'utf8'),
    readFile(
      new URL('../src/features/tools/components/presentations/PptUploader.vue', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/tools/components/presentations/PptList.vue', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/tools/composables/presentationController.ts', import.meta.url),
      'utf8'
    )
  ])

  assert.match(gallery, /usePageJob\('presentation_job'\)/)
  assert.match(gallery, /PageJobStatus/)
  assert.match(gallery, /result_summary\.presentation_id/)
  assert.match(uploader, /crypto\.randomUUID\(\)/)
  assert.match(list, /reconvertAttempts/)
  assert.match(store, /Idempotency-Key/)
  assert.match(store, /getPaginatedResults/)
  assert.doesNotMatch(store, /Promise<PresentationMutationResult>/)
})
