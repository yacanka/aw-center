import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (path) => readFile(new URL(path, import.meta.url), 'utf8')

test('stale CompDoc trace can create a credential-free current-source preview', async () => {
  const [history, refresh, service, preview, summaries] = await Promise.all([
    source('../src/components/compdoc/CompDocDccHistory.vue'),
    source('../src/components/compdoc/CompDocDccRefresh.vue'),
    source('../src/services/compdocTraceability.ts'),
    source('../src/components/dcc/DccCreationPreview.vue'),
    source('../src/services/jobSummaries.ts')
  ])

  assert.match(history, /CompDocDccRefresh/)
  assert.match(service, /refresh-preview\//)
  assert.match(service, /Idempotency-Key/)
  assert.match(service, /can_refresh_preview/)
  assert.match(refresh, /Create current-source preview/)
  assert.match(refresh, /dcc_job: job\.id/)
  assert.match(refresh, /source_archived/)
  assert.match(preview, /original DCC output remains unchanged/)
  assert.match(summaries, /DccCompdocRefreshSummary/)
})
