import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const componentUrl = new URL('../src/features/dcc/pages/DCCCreator.vue', import.meta.url)
const dccServiceUrl = new URL('../src/features/dcc/api/dccJobs.ts', import.meta.url)
const dccStoreUrl = new URL('../src/features/dcc/stores/dcc.ts', import.meta.url)
const dccRecordsUrl = new URL('../src/features/dcc/api/dccRecords.ts', import.meta.url)
const jiraSessionUrl = new URL('../src/features/dcc/api/jiraSession.ts', import.meta.url)
const storageServiceUrl = new URL('../src/shared/services/storage.ts', import.meta.url)
const routesUrl = new URL('../src/app/router/routes.ts', import.meta.url)
const menuUrl = new URL('../src/app/services/mainMenu.ts', import.meta.url)
const jobCenterUrl = new URL('../src/features/jobs/pages/JobCenter.vue', import.meta.url)
const watcherUrl = new URL('../src/features/dcc/pages/Watcher.vue', import.meta.url)
const sessionConsumerUrls = [
  '../src/features/dcc/pages/Jira.vue',
  '../src/features/dcc/pages/Watcher.vue',
  '../src/features/dcc/pages/DCCCreator.vue'
].map((path) => new URL(path, import.meta.url))
const jiraCredentialUrl = new URL('../src/features/dcc/pages/Jira.vue', import.meta.url)

test('DCC creator previews and confirms one durable snapshot without job secrets', async () => {
  const [component, service] = await Promise.all([
    readFile(componentUrl, 'utf8'),
    readFile(dccServiceUrl, 'utf8')
  ])

  assert.match(service, /dcc\/jobs\/create-document\/preview\//)
  assert.match(service, /dcc\/jobs\/create-document\/\$\{jobId\}\/confirm\//)
  assert.match(component, /previewDccDocumentJob/)
  assert.match(component, /confirmDccDocumentJob/)
  assert.match(component, /DccCreationPreview/)
  assert.match(component, /fetchJob/)
  assert.match(component, /downloadJob/)
  assert.doesNotMatch(component, /EventSource|createAuthenticatedEventSource/)
  assert.doesNotMatch(component, /\batob\s*\(/)
  assert.doesNotMatch(component, /localStorage|sessionStorage/)
  assert.doesNotMatch(component, /type="password"|JSESSIONID/)
  assert.doesNotMatch(service, /['"]\/dcc\/jobs\/create-document\/['"]/)
  assert.doesNotMatch(service, /compdoc_project|compdoc_ids|compdoc-recommendations/)
  assert.doesNotMatch(component, /DccCompdoc|compdocSelection/)
})

test('DCC confirmation UI exposes readiness, warnings, and expiry', async () => {
  const preview = await readFile(
    new URL('../src/features/dcc/components/DccCreationPreview.vue', import.meta.url),
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
    readFile(
      new URL('../src/features/jobs/components/JobDetailDrawer.vue', import.meta.url),
      'utf8'
    ),
    readFile(new URL('../src/features/jobs/components/JobListItem.vue', import.meta.url), 'utf8')
  ])
  const actionBlock = jobCenter.match(/async function runAction[\s\S]*?\n}/)?.[0] || ''

  assert.equal(actionBlock.match(/await action\(\)/g)?.length, 1)
  assert.match(drawer, /dcc_preview/)
  assert.match(drawer, /dcc_job: job.id/)
  assert.match(drawer, /v-if="job.status === 'awaiting_confirmation'"/)
  assert.match(listItem, /job.status === 'awaiting_confirmation'/)
})

test('JIRA credential is exchanged once and all other consumers use opaque connection state', async () => {
  const [store, jiraSession, storage, ...consumers] = await Promise.all([
    readFile(dccStoreUrl, 'utf8'),
    readFile(jiraSessionUrl, 'utf8'),
    readFile(storageServiceUrl, 'utf8'),
    ...sessionConsumerUrls.map((url) => readFile(url, 'utf8'))
  ])

  assert.doesNotMatch(storage, /jiraSession:/)
  assert.doesNotMatch(storage, /LEGACY_CREDENTIAL_KEYS|clearLegacyCredentialStorage/)
  assert.match(store, /jiraConnection: disconnectedJiraConnection/)
  assert.doesNotMatch(store, /readString|writeString|STORAGE_KEYS/)
  assert.match(jiraSession, /apiClient\.post<JiraConnection>/)
  assert.match(jiraSession, /JSESSIONID: credential/)
  assert.match(jiraSession, /apiClient\.get<JiraConnection>/)
  assert.match(jiraSession, /apiClient\.delete/)
  assert.doesNotMatch(
    `${store}\n${jiraSession}`,
    /jSessionId|getSessionId|setSessionId|importSessionId/
  )
  assert.doesNotMatch(consumers.slice(1).join('\n'), /JSESSIONID|getSessionId|sessionId/)
})

test('JIRA is the canonical navigation and route name', async () => {
  const [routes, menu] = await Promise.all([readFile(routesUrl, 'utf8'), readFile(menuUrl, 'utf8')])

  assert.match(menu, /menuItem\('JIRA', '\/jira', 'jira'/)
  assert.match(routes, /path: '\/jira',[\s\S]*name: 'jira'/)
  assert.doesNotMatch(routes, /path: '\/dcc'/)
  assert.match(routes, /features\/dcc\/pages\/Jira\.vue/)
})

test('DCC records and JIRA browser links are owned by canonical backend responses', async () => {
  const [watcher, records] = await Promise.all([
    readFile(watcherUrl, 'utf8'),
    readFile(dccRecordsUrl, 'utf8')
  ])
  const sources = `${watcher}\n${records}`

  assert.doesNotMatch(sources, /VITE_JIRA_SERVER|jiraServer/)
  assert.match(watcher, /row\.jira_issue_url/)
  assert.match(records, /apiClient\.get<PaginatedResponse<IDcc>>\('dcc\/records\/'/)
  assert.doesNotMatch(
    sources,
    /dcc\/(?:add|get_issue|create_issue|send_mail|upload|ecd_assessment|add_attachment|subtask_fields|create_queue)\//
  )
})

test('JIRA session fields cannot be populated as saved login passwords', async () => {
  const source = await readFile(jiraCredentialUrl, 'utf8')

  assert.match(source, /input-props/)
  assert.match(source, /autocomplete: 'one-time-code'/)
  assert.doesNotMatch(source, /autocomplete="off"/)
})

test('ECR uses the reviewed durable workflow and keeps retired direct actions closed', async () => {
  const [container, ecrTask, ecrService] = await Promise.all([
    readFile(new URL('../src/features/dcc/pages/Jira.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/features/dcc/components/EcrTask.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/features/dcc/api/ecrWorkflows.ts', import.meta.url), 'utf8')
  ])

  assert.doesNotMatch(container, /SubtaskGenerator|ExcelSubtaskGenerator/)
  assert.match(ecrTask, /api\/ecrWorkflows/)
  assert.match(ecrTask, /allowed_actions/)
  assert.match(ecrTask, /reconciliation_required/)
  assert.doesNotMatch(ecrTask, /apiClient|JSESSIONID/)
  assert.match(ecrService, /workflows\/ecr\//)
  assert.match(ecrService, /Idempotency-Key/)
  assert.doesNotMatch(
    [ecrTask, ecrService].join('\n'),
    /JSESSIONID|dcc\/(?:create_issue|send_mail|add_attachment|subtask_fields|create_queue)\//
  )
})
