import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const componentUrl = new URL('../src/views/dcc/DCCCreator.vue', import.meta.url)
const serviceUrl = new URL('../src/services/jobs.ts', import.meta.url)
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
    readFile(serviceUrl, 'utf8')
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
  assert.match(preview, /missing_recommended_fields/)
  assert.match(preview, /confirmation_expires_at/)
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
