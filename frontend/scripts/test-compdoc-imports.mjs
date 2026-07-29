import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import axios from 'axios'

const { confirmCompdocImport, previewCompdocImport } =
  await import('../src/services/compdocImports.ts')
const { shouldLoadCompdocHistory } = await import('../src/services/compdocHistory.ts')
const { buildCompdocUpdatePayload } = await import('../src/services/compdocPayload.ts')
const { fetchCompdocDashboard } = await import('../src/services/compdocDashboard.ts')
const { getCompdocReference, humanizeCompdocStatus, joinCompdocValues } =
  await import('../src/services/compdocWorkspace.ts')
const {
  checkCompDocRevision,
  downloadCompDocNotificationDraft,
  fetchCompDocTracking,
  formatTrackingTimestamp,
  saveCompDocTracking,
  sendCompDocNotification
} = await import('../src/services/compdocTracking.ts')
const {
  cloneCompDocNotificationRules,
  fetchCompDocNotificationPolicy,
  saveCompDocNotificationPolicy
} = await import('../src/services/compdocNotificationPolicy.ts')
const [tableSource, workspaceSource, workspaceController, overridesSource, issueColumnsSource] =
  await Promise.all([
    readFile(new URL('../src/views/CompDocTable.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocWorkspace.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/composables/compdoc/workspace.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/composables/compdoc/columnOverrides.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/composables/compdoc/issueColumns.ts', import.meta.url), 'utf8')
  ])
const identityFieldsSource = await readFile(
  new URL('../src/components/compdoc/CompDocIdentityFields.vue', import.meta.url),
  'utf8'
)
const workflowFieldsSource = await readFile(
  new URL('../src/components/compdoc/CompDocWorkflowFields.vue', import.meta.url),
  'utf8'
)
const overviewSource = await readFile(
  new URL('../src/components/compdoc/CompDocOverview.vue', import.meta.url),
  'utf8'
)
const popupSource = await readFile(
  new URL('../src/components/compdoc/CompDocPopup.vue', import.meta.url),
  'utf8'
)
const trackingPanelSource = await readFile(
  new URL('../src/components/compdoc/CompDocTrackingPanel.vue', import.meta.url),
  'utf8'
)
const optionalReasonSources = await Promise.all(
  [
    '../src/composables/compdoc/editor.ts',
    '../src/composables/compdoc/workspace.ts',
    '../src/components/compdoc/CompDocActivity.vue',
    '../src/components/compdoc/CompDocTransitionPanel.vue',
    '../src/components/compdoc/CompDocBulkActions.vue',
    '../src/components/compdoc/CompDocNotesFields.vue',
    '../src/components/compdoc/CompDocWorkPanel.vue'
  ].map((path) => readFile(new URL(path, import.meta.url), 'utf8'))
)
const activitySource = optionalReasonSources[2]
const transitionSource = optionalReasonSources[3]

test('builds safe operator-facing compliance document labels', () => {
  assert.equal(humanizeCompdocStatus('authority_approved'), 'Authority approved')
  assert.equal(humanizeCompdocStatus('to_be_re-submitted'), 'To be re submitted')
  assert.equal(getCompdocReference({ tech_doc_no: 'TD-42', cover_page_no: 'CP-7' }), 'TD-42')
  assert.equal(getCompdocReference({ tech_doc_no: '', cover_page_no: 'CP-7' }), 'CP-7')
  assert.equal(joinCompdocValues(['Panel A', '', 'Panel B']), 'Panel A, Panel B')
  assert.equal(joinCompdocValues(['CP-1', null, undefined]), 'CP-1')
  assert.equal(joinCompdocValues([]), 'Not assigned')
})

test('opens row workspaces without restoring an actions column', () => {
  assert.match(tableSource, /:row-props="rowProps"/)
  assert.match(workspaceController, /onDblclick: \(\) => openWorkspace\(document\)/)
  assert.doesNotMatch(workspaceController, /onClick: \(\) => openWorkspace\(document\)/)
  assert.match(tableSource, /Double-click a document row/)
  assert.match(workspaceController, /event\.key === 'Enter'/)
  assert.match(tableSource, /<CompDocWorkspace/)
  assert.match(workspaceSource, /Quick actions/)
  assert.match(overviewSource, /v-if="canEdit"/)
  assert.match(workspaceSource, /v-if="canDelete"/)
  assert.doesNotMatch(overviewSource, /Tracking & alerts/)
  assert.doesNotMatch(tableSource, /CompDocTrackingDrawer|trackingVisible|openTracking/)
  assert.doesNotMatch(overridesSource, /key: 'actions'/)
  assert.match(issueColumnsSource, /event\.stopPropagation\(\)/)
})

test('keeps the CompDoc filter header mounted for empty results', () => {
  assert.match(tableSource, /max-height="max\(320px, calc\(100vh - 300px\)\)"/)
  assert.match(tableSource, /:filter-icon-popover-props="table\.filterIconPopover"/)
})

test('separates the transition form from the always-visible Activity module', () => {
  assert.match(activitySource, /<n-timeline/)
  assert.doesNotMatch(activitySource, /n-collapse|Record transition|transitionCompdoc/)
  assert.match(workspaceSource, /Record transition/)
  assert.match(transitionSource, /transitionCompdoc/)
  assert.match(transitionSource, /Save transition/)
})

test('groups the wider document workspace into task-focused tabs', () => {
  assert.match(workspaceSource, /width="min\(720px, 96vw\)"/)
  assert.match(workspaceSource, /name="overview" tab="Overview"/)
  assert.match(workspaceSource, /name="tracking" tab="Tracking & Alerts"/)
  assert.match(workspaceSource, /name="ownership" tab="Ownership"/)
  assert.match(workspaceSource, /name="reviews" tab="Review & Approval"/)
  assert.match(workspaceSource, /name="transition"/)
  assert.match(workspaceSource, /tab="Transition"/)
  assert.match(workspaceSource, /name="activity" tab="Activity"/)
  assert.match(workspaceSource, /display-directive="show:lazy"/)
  assert.match(workspaceSource, /:show="show && activeTab === 'transition'"/)
  assert.match(workspaceSource, /:show="show && activeTab === 'tracking'"/)
  assert.match(workspaceSource, /:show="show && activeTab === 'activity'"/)
  assert.match(workspaceSource, /v-if="canEdit"[\s\S]*name="transition"/)
  assert.match(workspaceSource, /CompDocTrackingPanel/)
  assert.match(workspaceSource, /Tracking & alerts/)
  assert.doesNotMatch(trackingPanelSource, /<n-drawer/)
  assert.match(trackingPanelSource, /\{ immediate: true \}/)
})

test('full details closes from its mask while retaining editor close guards', () => {
  assert.match(popupSource, /:mask-closable="true"/)
  assert.match(popupSource, /@update:show="handleVisibilityChange"/)
})

test('consolidates tab and section guidance into one contextual help control', async () => {
  const contextHelp = await readFile(
    new URL('../src/components/compdoc/CompDocContextHelp.vue', import.meta.url),
    'utf8'
  )

  assert.equal(workspaceSource.match(/<CompDocContextHelp/g)?.length, 6)
  assert.equal(workspaceSource.match(/class="workspace-pane-heading"/g)?.length, 6)
  assert.match(workspaceSource, /<n-text strong>Tracking & alerts<\/n-text>/)
  assert.match(workspaceSource, /<n-text strong>Review & approval<\/n-text>/)
  assert.match(workspaceSource, /tab="overview"/)
  assert.match(workspaceSource, /tab="tracking"/)
  assert.match(workspaceSource, /:active="show && activeTab === 'tracking'"/)
  assert.doesNotMatch(workspaceSource, /CompDocTabLabel|CompDocHelpButton/)
  assert.match(contextHelp, /QuestionCircle20Regular/)
  assert.match(contextHelp, /:show="show"/)
  assert.match(contextHelp, /@update:show="show = \$event"/)
  assert.match(contextHelp, /aria-label="Help for current workspace tab"/)
  assert.match(contextHelp, /HELP_BY_TAB\[props\.tab\]/)
  assert.match(contextHelp, /if \(!active\) show\.value = false/)
  assert.match(contextHelp, /\{ flush: 'sync' \}/)
  assert.match(contextHelp, /overview:[\s\S]*tracking:[\s\S]*ownership:/)
  assert.match(contextHelp, /reviews:[\s\S]*transition:[\s\S]*activity:/)
  assert.match(contextHelp, /Document identity/)
  assert.match(contextHelp, /Responsible team/)
  assert.match(contextHelp, /Notification delivery/)
  assert.match(contextHelp, /Pending tasks/)
  assert.match(contextHelp, /Timeline/)
})

test('CompDoc ATA options are restricted to the selected panel', () => {
  assert.match(identityFieldsSource, /:options="ataOptions"/)
  assert.match(identityFieldsSource, /:disabled="readonly \|\| !compdoc\.panel"/)
  assert.match(identityFieldsSource, /\.filter\(\(panel\) => panel\.name === panelName\)/)
  assert.match(identityFieldsSource, /options\.length === 1 \? options\[0\]\.value : ''/)
  assert.doesNotMatch(identityFieldsSource, /:options="orgs\.getAtaOptions"/)
})

test('regular document updates exclude the workflow projection', () => {
  const payload = buildCompdocUpdatePayload({
    id: 'document-id',
    name: 'Document',
    status_flow: [{ status: 'authority_review', date: '29.07.2026' }]
  })

  assert.equal(payload.id, 'document-id')
  assert.equal('status_flow' in payload, false)
  assert.match(workflowFieldsSource, /<n-timeline/)
  assert.match(workflowFieldsSource, /Current status/)
  assert.match(workflowFieldsSource, /audit-controlled/)
})

test('document operation reasons are optional in the UI', () => {
  const combinedSource = optionalReasonSources.join('\n')

  assert.doesNotMatch(combinedSource, /meaningful .*reason/i)
  assert.doesNotMatch(combinedSource, /Required reason/)
  assert.match(combinedSource, /Reason \(optional\)/)
  assert.match(combinedSource, /Change reason \(optional\)/)
})

test('uses project-scoped tracking, DocProof, and notification endpoints', async () => {
  const response = trackingResponse()
  const loaded = await captureRequest(() => fetchCompDocTracking('özgür test', 'doc/id'), response)
  const saved = await captureRequest(
    () =>
      saveCompDocTracking('ozgur', 'document-id', {
        responsible_mode: 'automatic',
        responsible_person_ids: [],
        notification_enabled: true,
        notification_events: ['overdue']
      }),
    response
  )
  const checked = await captureRequest(() => checkCompDocRevision('ozgur', 'document-id'), response)
  const sent = await captureRequest(
    () => sendCompDocNotification('ozgur', 'document-id', 'revision_available'),
    { status: 'sent', event_type: 'revision_available', tracking: response }
  )

  assert.equal(loaded.url, '/%C3%B6zg%C3%BCr%20test/compdocs/doc%2Fid/tracking/')
  assert.equal(saved.url, '/ozgur/compdocs/document-id/tracking/')
  assert.equal(saved.method, 'put')
  assert.equal(checked.url, '/ozgur/compdocs/document-id/docproof/')
  assert.equal(sent.url, '/ozgur/compdocs/document-id/notifications/')
})

test('downloads a template-backed Outlook notification draft', async () => {
  const originalAdapter = axios.defaults.adapter
  let captured
  axios.defaults.adapter = async (config) => {
    captured = config
    return {
      data: new Blob(['msg']),
      status: 200,
      statusText: 'OK',
      headers: { 'content-disposition': 'attachment; filename="ozgur-TD-1-overdue.msg"' },
      config
    }
  }
  try {
    const draft = await downloadCompDocNotificationDraft('ozgur', 'document-id', 'overdue')
    assert.equal(captured.url, '/ozgur/compdocs/document-id/notifications/draft/')
    assert.equal(captured.method, 'post')
    assert.equal(captured.responseType, 'blob')
    assert.equal(draft.filename, 'ozgur-TD-1-overdue.msg')
  } finally {
    axios.defaults.adapter = originalAdapter
  }
})

test('presents automatic and editable Outlook notification choices together', async () => {
  const [panel, actions] = await Promise.all([
    readFile(
      new URL('../src/components/compdoc/CompDocTrackingPanel.vue', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/components/compdoc/CompDocNotificationActions.vue', import.meta.url),
      'utf8'
    )
  ])

  assert.match(panel, /CompDocNotificationActions/)
  assert.match(panel, /refreshPolicyProjection/)
  assert.match(panel, /@policy-saved="refreshPolicyProjection"/)
  assert.match(actions, /downloadCompDocNotificationDraft/)
  assert.match(actions, /saveBlobAsFile/)
  assert.match(actions, /Send automatically/)
  assert.match(actions, /Download Outlook draft/)
  assert.match(actions, /full HTML template/)
  assert.match(actions, /window\.\$dialog\.warning/)
  assert.match(actions, /Send notification/)
  assert.match(actions, /selectedState\.value\?\.applicable/)
  assert.match(actions, /Save tracking preferences/)
  assert.match(actions, /Event condition detected/)
  assert.match(actions, /escalation CC/)
  assert.match(actions, /selectedState\.policy_version/)
})

test('loads and publishes optimistic project notification policy revisions', async () => {
  const rules = notificationPolicyRules()
  const loaded = await captureRequest(() => fetchCompDocNotificationPolicy('özgür test'), {
    version: 0,
    rules
  })
  const saved = await captureRequest(
    () =>
      saveCompDocNotificationPolicy('ozgur', {
        expected_version: 2,
        change_note: 'Controlled escalation update',
        rules
      }),
    { version: 3, rules }
  )
  const cloned = cloneCompDocNotificationRules(rules)
  cloned.overdue.primary_titles.push('CVE')

  assert.equal(loaded.url, '/%C3%B6zg%C3%BCr%20test/compdocs/notification-policy/')
  assert.equal(saved.method, 'put')
  assert.equal(JSON.parse(saved.data).expected_version, 2)
  assert.deepEqual(rules.overdue.primary_titles, [])
})

test('exposes versioned policy management and immutable history in tracking', async () => {
  const [source, history] = await Promise.all([
    readFile(
      new URL('../src/components/compdoc/CompDocNotificationPolicyCard.vue', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/components/compdoc/CompDocNotificationHistory.vue', import.meta.url),
      'utf8'
    )
  ])

  assert.match(source, /Manage policy/)
  assert.match(source, /Publish new revision/)
  assert.match(source, /expected_version: policy\.value\.version/)
  assert.match(source, /Revision history/)
  assert.match(source, /formatApiError/)
  assert.match(source, /emit\('saved'\)/)
  assert.match(history, /escalation_recipient_count/)
  assert.match(history, /policy_version/)
})

test('formats persisted tracking timestamps for operators', () => {
  assert.equal(formatTrackingTimestamp(null), 'never')
  assert.doesNotMatch(formatTrackingTimestamp('2026-07-28T17:38:40Z'), /T|Z/)
})

test('explains the editable round-trip workbook and cleans download resources', async () => {
  const downloader = await readFile(
    new URL('../src/components/Downloader.vue', import.meta.url),
    'utf8'
  )

  assert.match(downloader, /dashboard workbook can be edited and imported directly back/)
  assert.match(downloader, /Professional dashboard with live KPIs and charts/)
  assert.match(downloader, /Every exported column is recognized by the current import contract/)
  assert.match(downloader, /encodeURIComponent\(String\(route\.params\.project/)
  assert.match(downloader, /URL\.revokeObjectURL\(urlObject\)/)
  assert.doesNotMatch(downloader, /setTimeout/)
})

test('loads CompDoc history when list responses omit the lazy-loaded field', () => {
  assert.equal(shouldLoadCompdocHistory({ id: 'document-id' }, true), true)
  assert.equal(shouldLoadCompdocHistory({ id: 'document-id', history: null }, true), true)
  assert.equal(shouldLoadCompdocHistory({ id: 'document-id', history: [] }, true), false)
  assert.equal(shouldLoadCompdocHistory({ id: 'document-id' }, false), false)
  assert.equal(shouldLoadCompdocHistory({}, true), false)
})

test('preview requests persistence-free impact metadata', async () => {
  const captured = await captureRequest(
    () => previewCompdocImport('/ozgur/compdocs/upload/', workbook()),
    previewResponse()
  )

  assert.equal(captured.url, '/ozgur/compdocs/upload/?preview=true')
  assert.equal(captured.data.get('confirmation_token'), null)
  assert.equal(captured.data.get('file').name, 'compdocs.xlsx')
})

test('confirmation sends the signed decision with the exact file', async () => {
  const file = workbook()
  const captured = await captureRequest(
    () => confirmCompdocImport('/ozgur/compdocs/upload/', file, 'signed-preview'),
    { message: 'Imported', invalid_documents: [] }
  )

  assert.equal(captured.url, '/ozgur/compdocs/upload/?confirm_import=true')
  assert.equal(captured.data.get('confirmation_token'), 'signed-preview')
  assert.equal(captured.data.get('file'), file)
})

test('import UI refreshes database-conflicted previews without discarding the workbook', async () => {
  const [component, composable] = await Promise.all([
    readFile(new URL('../src/components/compdoc/UploadPopup.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/composables/useCompdocImport.ts', import.meta.url), 'utf8')
  ])

  assert.match(component, /previewNotice/)
  assert.match(component, /protected against concurrent database changes/)
  assert.match(composable, /COMPDOC_IMPORT_DATABASE_CONFLICT/)
  assert.match(composable, /COMPDOC_IMPORT_PREVIEW_EXPIRED/)
  assert.match(composable, /await loadPreview\(pendingFile\.value, true\)/)
  assert.doesNotMatch(composable, /finally[\s\S]{0,100}resetUploadState/)
})

test('CompDoc UI gates every mutation with project model permissions', async () => {
  const [table, toolbar, remoteTable, popup] = await Promise.all([
    readFile(new URL('../src/views/CompDocTable.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocTableToolbar.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/composables/compdoc/remoteTable.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocPopup.vue', import.meta.url), 'utf8')
  ])

  assert.match(table, /permission\('view'\)/)
  assert.match(table, /permission\('add'\)/)
  assert.match(table, /permission\('change'\)/)
  assert.match(table, /permission\('delete'\)/)
  assert.match(table, /hasEffectiveRole\(project\.value, `\$\{action\}_compdoc`\)/)
  assert.match(table, /v-if="canImport"/)
  assert.match(table, /:can-delete="canDelete"/)
  assert.match(table, /initialFilters/)
  assert.match(toolbar, /v-if="canCreate"/)
  assert.doesNotMatch(toolbar, /CompDocBulkDelete/)
  assert.match(remoteTable, /dependencies\.project\.value, dependencies\.canView\.value/)
  assert.match(remoteTable, /dependencies\.initialFilters/)
  assert.match(popup, /popupMode ={2,3} 'view' && canEdit/)
})

test('CompDoc table rejects stale project and list responses', async () => {
  const [store, organizations] = await Promise.all([
    readFile(new URL('../src/stores/compdoc.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/stores/organizationProjects.ts', import.meta.url), 'utf8')
  ])

  assert.match(store, /const requestedProject = this\.projectName/)
  assert.match(store, /const requestId = \+\+this\.listRequestId/)
  assert.match(store, /this\.projectName === requestedProject && this\.listRequestId === requestId/)
  assert.match(
    organizations,
    /if \(state\.project === requestedProject\) state\.panels = getPaginatedResults<IPanel>\(data\)/
  )
})

test('dashboard requests complete project analytics with cancellation support', async () => {
  const controller = new AbortController()
  const captured = await captureRequest(
    () => fetchCompdocDashboard('project name', controller.signal),
    dashboardResponse()
  )

  assert.equal(captured.url, '/project%20name/compdocs/dashboard/')
  assert.equal(captured.signal, controller.signal)
})

test('dashboard isolates paginated table state and stale project responses', async () => {
  const [applicationHome, complianceHome, routes, menu, composable, dashboard, riskDashboard] =
    await Promise.all([
      readFile(new URL('../src/views/Home.vue', import.meta.url), 'utf8'),
      readFile(new URL('../src/views/compdoc/Home.vue', import.meta.url), 'utf8'),
      readFile(new URL('../src/router/routes.ts', import.meta.url), 'utf8'),
      readFile(new URL('../src/services/mainMenu.ts', import.meta.url), 'utf8'),
      readFile(new URL('../src/composables/compdoc/dashboard.ts', import.meta.url), 'utf8'),
      readFile(
        new URL('../src/components/compdoc/ComplianceDashboard.vue', import.meta.url),
        'utf8'
      ),
      readFile(
        new URL('../src/components/compdoc/CompDocRiskDashboard.vue', import.meta.url),
        'utf8'
      )
    ])

  assert.match(applicationHome, /ActionCenter/)
  assert.doesNotMatch(applicationHome, /ComplianceDashboard/)
  assert.match(complianceHome, /ComplianceDashboard/)
  assert.match(routes, /name: 'compdocsHome',[\s\S]*path: 'home'/)
  assert.match(menu, /menuItem\('Home', '\/compdocs\/home', 'compdocsHome'/)
  assert.match(composable, /activeController\?\.abort\(\)/)
  assert.match(composable, /sequence === requestSequence/)
  assert.match(dashboard, /dataQualityIssues/)
  assert.match(dashboard, /invalid_status_flow/)
  assert.match(dashboard, /CompDocRiskDashboard/)
  assert.match(dashboard, /CompDocTrackingSummary/)
  assert.match(riskDashboard, /priority\.signals/)
  assert.match(riskDashboard, /risk\.policy/)
  assert.match(riskDashboard, /query: \{ name \}/)
})

test('CompDoc charts use responsive modern Chart.js rendering paths', async () => {
  const [graph, status, timeline, legacyStore] = await Promise.all([
    readFile(new URL('../src/components/compdoc/Graph.vue', import.meta.url), 'utf8'),
    readFile(
      new URL('../src/components/compdoc/CompDocStatusDashboard.vue', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/components/compdoc/CompDocTimelineDashboard.vue', import.meta.url),
      'utf8'
    ),
    readFile(new URL('../src/stores/chartStore.js', import.meta.url), 'utf8')
  ])

  assert.match(graph, /display-directive="if"/)
  assert.match(graph, /buildClientCompdocSummary/)
  assert.match(status, /createStatusChartData/)
  assert.match(timeline, /createTimelineChartData/)
  assert.doesNotMatch(legacyStore, /Outlabels|\$compdocStore/)
})

test('exposes lifecycle, ownership, review, activity, and bounded bulk workflows', async () => {
  const [service, workspace, table, bulk, activity, transition] = await Promise.all([
    readFile(new URL('../src/services/compdocLifecycle.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocWorkspace.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/CompDocTable.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocBulkActions.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocActivity.vue', import.meta.url), 'utf8'),
    readFile(
      new URL('../src/components/compdoc/CompDocTransitionPanel.vue', import.meta.url),
      'utf8'
    )
  ])

  assert.match(service, /\/activity\//)
  assert.match(service, /\/transitions\//)
  assert.match(service, /\/reviews\//)
  assert.match(service, /\/work\//)
  assert.match(service, /\/bulk\//)
  assert.match(workspace, /CompDocWorkPanel/)
  assert.match(workspace, /CompDocReviewPanel/)
  assert.match(workspace, /CompDocActivity/)
  assert.match(table, /type: 'selection'/)
  assert.match(bulk, /versioned/)
  assert.match(activity, /fetchCompdocActivity/)
  assert.doesNotMatch(activity, /Record transition/)
  assert.match(workspace, /Record transition/)
})

async function captureRequest(callback, responseData) {
  const originalAdapter = axios.defaults.adapter
  let captured
  axios.defaults.adapter = async (config) => {
    captured = config
    return { data: responseData, status: 200, statusText: 'OK', headers: {}, config }
  }
  try {
    await callback()
    return captured
  } finally {
    axios.defaults.adapter = originalAdapter
  }
}

function workbook() {
  return new File(['workbook'], 'compdocs.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  })
}

function previewResponse() {
  return {
    header_row: 1,
    mapped_columns: [],
    unmapped_columns: [],
    missing_columns: [],
    invalid_documents: [],
    created_count: 1,
    updated_count: 0,
    unchanged_count: 0,
    rejected_count: 0,
    confirmation_token: 'signed-preview',
    database_state_protected: true
  }
}

function dashboardResponse() {
  return {
    document_count: 0,
    status_counts: {},
    panels: [],
    pending_days: { authority: 0, ubm: 0, aw: 0 },
    timeline: { scheduled: [], actual: [], today: [], last_scheduled: null, last_actual: null },
    performance: {},
    risk: {
      counts: { high: 0, medium: 0, low: 0, none: 0 },
      at_risk_count: 0,
      average_score: 0,
      max_score: 0,
      priorities: [],
      policy: {
        version: 1,
        high_score: 60,
        medium_score: 30,
        long_wait_days: 30,
        authority_aging_days: 14,
        max_score: 100,
        priority_limit: 25
      }
    },
    tracking: {
      configured_count: 0,
      notification_enabled_count: 0,
      revision_available_count: 0,
      delivery_failure_count: 0
    },
    data_quality: { issue_count: 0 },
    generated_at: new Date(0).toISOString()
  }
}

function trackingResponse() {
  return {
    document: {
      id: 'document-id',
      name: 'Manual',
      ata: '21-00',
      panel: 'Flight',
      tech_doc_no: 'TD-1',
      tech_doc_issue: '1',
      delivered_tech_doc_issue: '',
      status: 'to_be_issued',
      ubm_target_date: null
    },
    responsible_mode: 'automatic',
    responsible_person_ids: [],
    responsibles: [],
    candidate_responsibles: [],
    configured: false,
    notification_enabled: false,
    notification_events: [],
    event_options: [],
    event_states: [],
    docproof: { status: 'never_checked', issue: '', checked_at: null },
    recent_notifications: []
  }
}

function notificationPolicyRules() {
  const rule = {
    reminder_interval_hours: 0,
    failure_retry_hours: 1,
    primary_titles: [],
    escalation_titles: [],
    escalate_after_hours: 0
  }
  return {
    overdue: { ...rule, primary_titles: [], escalation_titles: [] },
    due_soon: { ...rule, primary_titles: [], escalation_titles: [] },
    revision_available: { ...rule, primary_titles: [], escalation_titles: [] }
  }
}
