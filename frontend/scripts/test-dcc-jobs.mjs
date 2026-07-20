import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const componentUrl = new URL('../src/views/dcc/DCCCreator.vue', import.meta.url)
const dccServiceUrl = new URL('../src/services/dccJobs.ts', import.meta.url)
const jobCenterUrl = new URL('../src/views/JobCenter.vue', import.meta.url)
const sessionConsumerUrls = [
  '../src/views/ECDContainer.vue',
  '../src/views/dcc/SubtaskGenerator.vue',
  '../src/views/dcc/ExcelSubtaskGenerator.vue',
  '../src/views/dcc/Watcher.vue',
  '../src/components/dcc/EmailPopup.vue',
  '../src/components/dcc/UploadPopup.vue'
].map((path) => new URL(path, import.meta.url))
const temporaryCredentialUrls = [
  '../src/views/dcc/DCCCreator.vue',
  '../src/views/ECDContainer.vue',
  '../src/components/outlook/EcrTask.vue',
  '../src/components/jobs/JiraDraftPreflightPanel.vue'
].map((path) => new URL(path, import.meta.url))

test('DCC creator previews and confirms one durable snapshot without browser secrets', async () => {
  const [component, service] = await Promise.all([
    readFile(componentUrl, 'utf8'),
    readFile(dccServiceUrl, 'utf8')
  ])

  assert.match(service, /\/dcc\/jobs\/create-document\/preview\//)
  assert.match(service, /\/dcc\/jobs\/create-document\/\$\{jobId\}\/confirm\//)
  assert.match(component, /previewDccDocumentJob/)
  assert.match(component, /confirmDccDocumentJob/)
  assert.match(component, /DccCreationPreview/)
  assert.match(component, /fetchJob/)
  assert.match(component, /downloadJob/)
  assert.doesNotMatch(component, /EventSource|createAuthenticatedEventSource/)
  assert.doesNotMatch(component, /\batob\s*\(/)
  assert.doesNotMatch(component, /localStorage|sessionStorage/)
  assert.doesNotMatch(service, /['"]\/dcc\/jobs\/create-document\/['"]/)
})

test('DCC confirmation UI exposes readiness, impact, warnings, and expiry', async () => {
  const preview = await readFile(
    new URL('../src/components/dcc/DccCreationPreview.vue', import.meta.url),
    'utf8'
  )

  assert.match(preview, /awaiting_confirmation/)
  assert.match(preview, /template successfully rendered/)
  assert.match(preview, /panel_count/)
  assert.match(preview, /readinessScore/)
  assert.match(preview, /readinessChecks/)
  assert.match(preview, /requiresAcknowledgement/)
  assert.match(preview, /warningsAcknowledged/)
  assert.match(preview, /confirmation_expires_at/)
  assert.match(preview, /compliance_document_count/)
  assert.match(preview, /compliance_document_fingerprint/)
  assert.match(preview, /recovery_hint/)
  assert.match(preview, /Confirm and queue exact snapshot/)

  const service = await readFile(dccServiceUrl, 'utf8')
  assert.match(service, /acknowledged_warning_codes: warningCodes/)
})

test('CompDoc selection crosses into DCC as a bounded server-verified source', async () => {
  const [table, bridge, creator, service] = await Promise.all([
    readFile(new URL('../src/views/CompDocTable.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocDccBridge.vue', import.meta.url), 'utf8'),
    readFile(componentUrl, 'utf8'),
    readFile(dccServiceUrl, 'utf8')
  ])

  assert.match(table, /type: 'selection'/)
  assert.match(table, /MAX_DCC_COMPDOC_SELECTION = 50/)
  assert.match(table, /dcc.*add_jira_dcc/)
  assert.match(bridge, /compdoc_project/)
  assert.match(bridge, /compdocs/)
  assert.match(creator, /compdocSelection/)
  assert.match(service, /compdoc_ids/)
  assert.match(service, /compdoc_project/)
})

test('DCC preview offers explainable CompDoc recommendations without automatic linking', async () => {
  const [creator, preview, recommendations, service, summaries] = await Promise.all([
    readFile(componentUrl, 'utf8'),
    readFile(new URL('../src/components/dcc/DccCreationPreview.vue', import.meta.url), 'utf8'),
    readFile(
      new URL('../src/components/dcc/DccCompdocRecommendations.vue', import.meta.url),
      'utf8'
    ),
    readFile(dccServiceUrl, 'utf8'),
    readFile(new URL('../src/services/jobSummaries.ts', import.meta.url), 'utf8')
  ])

  assert.match(preview, /DccCompdocRecommendations/)
  assert.match(preview, /recommendation-preview/)
  assert.match(creator, /@recommendation-preview="setCurrentJob"/)
  assert.match(recommendations, /deterministic and evidence-based/)
  assert.match(recommendations, /selectedIds = ref<string\[\]>\(\[\]\)/)
  assert.match(recommendations, /Create enriched preview/)
  assert.match(recommendations, /item\.reasons/)
  assert.match(service, /compdoc-recommendations\//)
  assert.match(service, /Idempotency-Key/)
  assert.match(summaries, /DccCompdocRecommendation/)
})

test('CompDoc details expose permission-aware reverse DCC provenance', async () => {
  const [details, history, service] = await Promise.all([
    readFile(new URL('../src/components/compdoc/DetailedInfo.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocDccHistory.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/services/compdocTraceability.ts', import.meta.url), 'utf8')
  ])

  assert.match(details, /view_jira_dcc/)
  assert.match(details, /CompDocDccHistory/)
  assert.match(service, /\/dcc\/compdoc-traceability\//)
  assert.match(service, /compdoc_id/)
  assert.match(history, /is_current_version/)
  assert.match(history, /source_change\.changed_fields/)
  assert.match(history, /sourceChangeMessage/)
  assert.match(service, /TraceSourceComparisonStatus/)
  assert.match(service, /changed_field_count/)
  assert.match(history, /source_fingerprint/)
  assert.match(history, /Open in Job Center/)
  assert.match(history, /AbortController/)
})

test('Action Center deep-links stale DCC sources to the exact CompDoc history', async () => {
  const [actionCenter, actionService, table] = await Promise.all([
    readFile(new URL('../src/components/ActionCenter.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/services/actionCenter.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/CompDocTable.vue', import.meta.url), 'utf8')
  ])

  assert.match(actionService, /compdoc_trace/)
  assert.match(actionCenter, /DCC source/)
  assert.match(table, /route\.query\.compdoc/)
  assert.match(table, /id: linkedCompdocId\.value/)
  assert.match(table, /openLinkedCompdoc/)
  assert.match(table, /openModal\(document, 'view'\)/)
})

test('CompDoc updates review DCC impact before writing a versioned source', async () => {
  const [popup, impact, model] = await Promise.all([
    readFile(new URL('../src/components/compdoc/CompDocPopup.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocChangeImpact.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/models/compdocs.ts', import.meta.url), 'utf8')
  ])

  assert.match(model, /source_history_id\?: number/)
  assert.match(popup, /CompDocChangeImpact/)
  assert.match(popup, /CompDocDccHistory/)
  assert.match(popup, /:disabled="updateBlocked"/)
  assert.match(impact, /fetchCompdocDccTraces/)
  assert.match(impact, /I reviewed this impact/)
  assert.match(impact, /existing outputs stay immutable/)
  assert.match(impact, /AbortController/)
})

test('Job Center performs one action and links pending DCC previews back to review', async () => {
  const [jobCenter, drawer, listItem] = await Promise.all([
    readFile(jobCenterUrl, 'utf8'),
    readFile(new URL('../src/components/jobs/JobDetailDrawer.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/jobs/JobListItem.vue', import.meta.url), 'utf8')
  ])
  const actionBlock = jobCenter.match(/async function runAction[\s\S]*?\n}/)?.[0] || ''

  assert.equal(actionBlock.match(/await action\(\)/g)?.length, 1)
  assert.match(drawer, /dcc_preview/)
  assert.match(drawer, /dcc_job: job.id/)
  assert.match(drawer, /v-if="job.status === 'awaiting_confirmation'"/)
  assert.match(listItem, /job.status === 'awaiting_confirmation'/)
})

test('DCC tools keep JIRA sessions in memory instead of browser storage', async () => {
  const sources = await Promise.all(sessionConsumerUrls.map((url) => readFile(url, 'utf8')))

  assert.doesNotMatch(sources.join('\n'), /jira>session_id/)
})

test('temporary JIRA credentials cannot be populated as saved login passwords', async () => {
  const sources = await Promise.all(temporaryCredentialUrls.map((url) => readFile(url, 'utf8')))

  for (const source of sources) {
    assert.match(source, /input-props/)
    assert.match(source, /autocomplete: 'one-time-code'/)
    assert.doesNotMatch(source, /autocomplete="off"/)
  }
})
