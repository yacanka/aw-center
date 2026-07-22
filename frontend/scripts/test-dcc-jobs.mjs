import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const componentUrl = new URL('../src/views/dcc/DCCCreator.vue', import.meta.url)
const dccServiceUrl = new URL('../src/services/dccJobs.ts', import.meta.url)
const dccStoreUrl = new URL('../src/stores/dcc.ts', import.meta.url)
const storageServiceUrl = new URL('../src/services/storage.ts', import.meta.url)
const routesUrl = new URL('../src/router/routes.ts', import.meta.url)
const menuUrl = new URL('../src/services/mainMenu.ts', import.meta.url)
const jobCenterUrl = new URL('../src/views/JobCenter.vue', import.meta.url)
const watcherUrl = new URL('../src/views/dcc/Watcher.vue', import.meta.url)
const detailedInfoUrl = new URL('../src/components/dcc/DetailedInfo.vue', import.meta.url)
const sessionConsumerUrls = [
  '../src/views/JiraContainer.vue',
  '../src/views/dcc/SubtaskGenerator.vue',
  '../src/views/dcc/ExcelSubtaskGenerator.vue',
  '../src/views/dcc/Watcher.vue',
  '../src/components/dcc/EmailPopup.vue',
  '../src/components/dcc/UploadPopup.vue'
].map((path) => new URL(path, import.meta.url))
const jiraCredentialUrls = [
  '../src/views/dcc/DCCCreator.vue',
  '../src/views/JiraContainer.vue',
  '../src/components/outlook/EcrTask.vue',
  '../src/components/jobs/JiraDraftPreflightPanel.vue'
].map((path) => new URL(path, import.meta.url))

test('DCC creator previews and confirms one durable snapshot without job secrets', async () => {
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
  assert.doesNotMatch(service, /compdoc_project|compdoc_ids|compdoc-recommendations/)
  assert.doesNotMatch(component, /DccCompdoc|compdocSelection/)
})

test('DCC confirmation UI exposes readiness, warnings, and expiry', async () => {
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
  assert.match(preview, /recovery_hint/)
  assert.match(preview, /Confirm and queue exact snapshot/)

  const service = await readFile(dccServiceUrl, 'utf8')
  assert.match(service, /acknowledged_warning_codes: warningCodes/)
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

test('JIRA tools reuse one locally persisted session without direct storage access', async () => {
  const [store, storage, ...consumers] = await Promise.all([
    readFile(dccStoreUrl, 'utf8'),
    readFile(storageServiceUrl, 'utf8'),
    ...sessionConsumerUrls.map((url) => readFile(url, 'utf8'))
  ])

  assert.match(storage, /jiraSession: 'jira_session_id'/)
  assert.match(store, /readString\(STORAGE_KEYS\.jiraSession\)/)
  assert.match(store, /writeString\(STORAGE_KEYS\.jiraSession/)
  assert.match(store, /removeKey\(STORAGE_KEYS\.jiraSession\)/)
  assert.doesNotMatch(consumers.join('\n'), /localStorage|sessionStorage/)
})

test('JIRA is the canonical navigation and route name', async () => {
  const [routes, menu] = await Promise.all([readFile(routesUrl, 'utf8'), readFile(menuUrl, 'utf8')])

  assert.match(menu, /menuItem\('JIRA', '\/jira', 'jira'/)
  assert.match(routes, /path: '\/jira',[\s\S]*name: 'jira'/)
  assert.doesNotMatch(routes, /path: '\/dcc'/)
  assert.match(routes, /JiraContainer\.vue/)
})

test('JIRA browser links are owned by backend API responses', async () => {
  const [watcher, detailedInfo, store] = await Promise.all([
    readFile(watcherUrl, 'utf8'),
    readFile(detailedInfoUrl, 'utf8'),
    readFile(dccStoreUrl, 'utf8')
  ])
  const sources = `${watcher}\n${detailedInfo}\n${store}`

  assert.doesNotMatch(sources, /VITE_JIRA_SERVER|jiraServer/)
  assert.match(watcher, /row\.jira_issue_url/)
  assert.match(detailedInfo, /subtasks\[index\]\.jira_issue_url/)
  assert.match(store, /JiraIssueResponse/)
})

test('JIRA session fields cannot be populated as saved login passwords', async () => {
  const sources = await Promise.all(jiraCredentialUrls.map((url) => readFile(url, 'utf8')))

  for (const source of sources) {
    assert.match(source, /input-props/)
    assert.match(source, /autocomplete: 'one-time-code'/)
    assert.doesNotMatch(source, /autocomplete="off"/)
  }
})
