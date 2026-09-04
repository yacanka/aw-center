import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'vitest'
import { apiClient as axios } from '../src/shared/api/http.ts'

const { confirmCompdocImport, previewCompdocImport } =
  await import('../src/features/compliance/api/compdocImports.ts')
const { shouldLoadCompdocHistory } =
  await import('../src/features/compliance/api/compdocHistory.ts')
const { buildCompdocCreatePayload, buildCompdocUpdatePayload } =
  await import('../src/features/compliance/api/compdocPayload.ts')
const { normalizeCompdoc, normalizeCompdocFields } =
  await import('../src/features/compliance/api/compdocContract.ts')
const { fetchCompdocDashboard } = await import('../src/features/compliance/api/compdocDashboard.ts')
const { fetchCompdocActivity } = await import('../src/features/compliance/api/compdocLifecycle.ts')
const { getCompdocReference, humanizeCompdocStatus, joinCompdocValues } =
  await import('../src/features/compliance/api/compdocWorkspace.ts')
const { fetchCompDocTracking, formatTrackingTimestamp, saveCompDocTracking } =
  await import('../src/features/compliance/api/compdocTracking.ts')
const {
  cloneCompDocNotificationRules,
  fetchCompDocNotificationPolicy,
  saveCompDocNotificationPolicy
} = await import('../src/features/compliance/api/compdocNotificationPolicy.ts')
const [tableSource, workspaceSource, workspaceController, overridesSource, issueColumnsSource] =
  await Promise.all([
    readFile(new URL('../src/features/compliance/pages/CompDocTable.vue', import.meta.url), 'utf8'),
    readFile(
      new URL('../src/features/compliance/components/CompDocWorkspace.vue', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/compliance/composables/workspace.ts', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/compliance/composables/columnOverrides.ts', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/compliance/composables/issueColumns.ts', import.meta.url),
      'utf8'
    )
  ])
const identityFieldsSource = await readFile(
  new URL('../src/features/compliance/components/CompDocIdentityFields.vue', import.meta.url),
  'utf8'
)
const workflowFieldsSource = await readFile(
  new URL('../src/features/compliance/components/CompDocWorkflowFields.vue', import.meta.url),
  'utf8'
)
const overviewSource = await readFile(
  new URL('../src/features/compliance/components/CompDocOverview.vue', import.meta.url),
  'utf8'
)
const popupSource = await readFile(
  new URL('../src/features/compliance/components/CompDocPopup.vue', import.meta.url),
  'utf8'
)
const trackingPanelSource = await readFile(
  new URL('../src/features/compliance/components/CompDocTrackingPanel.vue', import.meta.url),
  'utf8'
)
const optionalReasonSources = await Promise.all(
  [
    '../src/features/compliance/composables/editor.ts',
    '../src/features/compliance/composables/workspace.ts',
    '../src/features/compliance/components/CompDocActivity.vue',
    '../src/features/compliance/components/CompDocTransitionPanel.vue',
    '../src/features/compliance/components/CompDocNotesFields.vue',
    '../src/features/compliance/components/CompDocWorkPanel.vue'
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
    new URL('../src/features/compliance/components/CompDocContextHelp.vue', import.meta.url),
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

test('CompDoc panel names remain visible and ATA is derived from the selected panel', () => {
  assert.match(identityFieldsSource, /:options="panelOptions"/)
  assert.match(identityFieldsSource, /const options = orgs\.getCompdocPanelOptions/)
  assert.match(identityFieldsSource, /props\.compdoc\.panel_name/)
  assert.match(identityFieldsSource, /:value="compdoc\.ata \|\| ''"/)
  assert.match(identityFieldsSource, /placeholder="—" readonly/)
  assert.match(identityFieldsSource, /\.filter\(\(panel\) => panel\.id === panelId\)/)
  assert.match(
    identityFieldsSource,
    /options\.length === 1 \? String\(options\[0\]\.value\) : null/
  )
  assert.doesNotMatch(identityFieldsSource, /:options="orgs\.getAtaOptions"/)
})

test('regular document updates send only canonical editable fields and version', () => {
  const payload = buildCompdocUpdatePayload({
    id: 'document-id',
    version: 3,
    name: 'Document',
    panel: 4,
    cover_page_no: 'CP-7',
    cover_page_issue: 'A',
    path: 'controlled/reference',
    signature_panel: [],
    requirements: [],
    status_flow: [{ status: 'authority_review', date: '29.07.2026' }]
  })

  assert.equal(payload.version, 3)
  assert.equal(payload.name, 'Document')
  assert.deepEqual(payload.cover_page, { number: 'CP-7', issue: 'A' })
  assert.equal(payload.path, 'controlled/reference')
  assert.equal('id' in payload, false)
  assert.equal('status_flow' in payload, false)
  const createPayload = buildCompdocCreatePayload({
    ...payload,
    cover_page_no: 'CP-7',
    cover_page_issue: 'A',
    status_flow: []
  })
  assert.equal('version' in createPayload, false)
  assert.match(workflowFieldsSource, /<n-timeline/)
  assert.match(workflowFieldsSource, /Current status/)
  assert.match(workflowFieldsSource, /audit-controlled/)
})

test('normalizes canonical nested document and bounded field contracts', () => {
  const document = normalizeCompdoc({
    id: 'f8af884c-78dc-4eb4-930a-2468b66b26f6',
    project_slug: 'ozgur',
    panel: 7,
    panel_name: 'Flight Controls',
    ata: '27-00',
    path: 'controlled/reference',
    cover_page: { number: 'CP-7', issue: 'A' },
    name: 'Flight manual',
    signature_panel: ['Panel A'],
    requirements: ['CS-25'],
    version: 4,
    created_at: '2026-08-01T10:00:00Z'
  })
  const fields = normalizeCompdocFields({
    schema_version: 3,
    project: 'ozgur',
    fields: [
      {
        key: 'panel',
        label: 'Panel',
        required: false,
        read_only: false,
        filter_kind: 'select',
        sortable: true,
        option_source: 'panels'
      },
      { key: 'cover_page', label: 'Cover Page', required: true, read_only: false },
      {
        key: 'path',
        label: 'Path',
        required: false,
        read_only: false,
        filter_kind: 'text',
        sortable: true
      }
    ]
  })

  assert.equal(document.project, 'ozgur')
  assert.equal(document.panel, 7)
  assert.equal(document.panel_name, 'Flight Controls')
  assert.equal(document.ata, '27-00')
  assert.equal(document.cover_page_no, 'CP-7')
  assert.equal(document.cover_page_issue, 'A')
  assert.equal(document.path, 'controlled/reference')
  assert.deepEqual(
    fields.fields.map((field) => field.key),
    ['panel', 'cover_page_no', 'cover_page_issue', 'path']
  )
  assert.equal(fields.fields.find((field) => field.key === 'panel').filter_kind, 'select')
  assert.equal(fields.fields.find((field) => field.key === 'cover_page_no').sortable, true)
})

test('document operation reasons are optional in the UI', () => {
  const combinedSource = optionalReasonSources.join('\n')

  assert.doesNotMatch(combinedSource, /meaningful .*reason/i)
  assert.doesNotMatch(combinedSource, /Required reason/)
  assert.match(combinedSource, /Reason \(optional\)/)
  assert.match(combinedSource, /Change reason \(optional\)/)
})

test('uses only the canonical project-scoped tracking resource', async () => {
  const response = trackingResponse()
  const loaded = await captureRequest(() => fetchCompDocTracking('özgür test', 'doc-id'), response)
  const saved = await captureRequest(
    () =>
      saveCompDocTracking('ozgur', 'document-id', {
        responsible_mode: 'automatic',
        responsible_person_ids: [],
        notification_enabled: true,
        notification_events: ['overdue'],
        version: 4
      }),
    response
  )

  assert.equal(loaded.url, 'projects/%C3%B6zg%C3%BCr%20test/compliance-documents/doc-id/tracking/')
  assert.equal(saved.url, 'projects/ozgur/compliance-documents/document-id/tracking/')
  assert.equal(saved.method, 'put')
  assert.equal(JSON.parse(saved.data).version, 4)

  await assert.rejects(
    () => fetchCompDocTracking('ozgur', 'doc/id'),
    /cannot contain traversal or encoded separators/
  )
})

test('loads and publishes canonical project notification policy revisions', async () => {
  const rules = notificationPolicyRules()
  const loaded = await captureRequest(() => fetchCompDocNotificationPolicy('özgür test'), {
    version: 0,
    event_rules: rules
  })
  const saved = await captureRequest(
    () =>
      saveCompDocNotificationPolicy('ozgur', {
        version: 0,
        change_note: 'Controlled escalation update',
        event_rules: rules
      }),
    { version: 3, event_rules: rules }
  )
  const cloned = cloneCompDocNotificationRules(rules)
  cloned.overdue.enabled = false

  assert.equal(
    loaded.url,
    'projects/%C3%B6zg%C3%BCr%20test/compliance-documents/notification-policy/'
  )
  assert.equal(saved.method, 'put')
  assert.equal(JSON.parse(saved.data).version, 0)
  assert.equal(JSON.parse(saved.data).event_rules.overdue.enabled, true)
  assert.equal(rules.overdue.enabled, true)
})

test('fails closed for removed notification send, draft, and history actions', async () => {
  const source = await readFile(
    new URL(
      '../src/features/compliance/components/CompDocNotificationPolicyCard.vue',
      import.meta.url
    ),
    'utf8'
  )

  assert.match(source, /Manage policy/)
  assert.match(source, /Publish revision/)
  assert.match(source, /event_rules: draft\.value/)
  assert.match(source, /formatApiError/)
  assert.match(source, /emit\('saved'\)/)
  assert.doesNotMatch(trackingPanelSource, /notifications\/|notifications\/draft|sendNow/)
})

test('formats persisted tracking timestamps for operators', () => {
  assert.equal(formatTrackingTimestamp(null), 'never')
  assert.doesNotMatch(formatTrackingTimestamp('2026-07-28T17:38:40Z'), /T|Z/)
})

test('explains the bounded register export and cleans download resources', async () => {
  const downloader = await readFile(
    new URL('../src/features/compliance/components/Downloader.vue', import.meta.url),
    'utf8'
  )

  assert.match(downloader, /current register snapshot is ready/)
  assert.match(downloader, /all active documents/)
  assert.match(downloader, /Import validation is a separate preview\/confirm flow/)
  assert.doesNotMatch(downloader, /imported directly back|live KPIs/)
  assert.match(downloader, /String\(route\.params\.project/)
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
    () => previewCompdocImport('projects/ozgur/compliance-documents/', workbook()),
    previewResponse()
  )

  assert.equal(captured.url, 'projects/ozgur/compliance-documents/imports/preview/')
  assert.equal(captured.data.get('confirmation_token'), null)
  assert.equal(captured.data.get('file').name, 'compdocs.xlsx')
})

test('confirmation sends the signed decision with the exact file', async () => {
  const file = workbook()
  const captured = await captureRequest(
    () => confirmCompdocImport('projects/ozgur/compliance-documents/', file, 'signed-preview'),
    { message: 'Imported', invalid_documents: [] }
  )

  assert.equal(captured.url, 'projects/ozgur/compliance-documents/imports/confirm/')
  assert.equal(captured.data.get('confirmation_token'), 'signed-preview')
  assert.equal(captured.data.get('file'), file)
})

test('import UI refreshes database-conflicted previews without discarding the workbook', async () => {
  const [component, composable] = await Promise.all([
    readFile(
      new URL('../src/features/compliance/components/UploadPopup.vue', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/compliance/composables/useCompdocImport.ts', import.meta.url),
      'utf8'
    )
  ])

  assert.match(component, /previewNotice/)
  assert.match(component, /protected against concurrent database changes/)
  assert.match(composable, /VERSION_CONFLICT/)
  assert.match(composable, /COMPDOC_IMPORT_PREVIEW_EXPIRED/)
  assert.match(composable, /await loadPreview\(pendingFile\.value, true\)/)
  assert.doesNotMatch(composable, /finally[\s\S]{0,100}resetUploadState/)
})

test('CompDoc UI gates every mutation with canonical project-domain roles', async () => {
  const [table, toolbar, remoteTable, popup] = await Promise.all([
    readFile(new URL('../src/features/compliance/pages/CompDocTable.vue', import.meta.url), 'utf8'),
    readFile(
      new URL('../src/features/compliance/components/CompDocTableToolbar.vue', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/compliance/composables/remoteTable.ts', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/compliance/components/CompDocPopup.vue', import.meta.url),
      'utf8'
    )
  ])

  assert.match(table, /permission\('viewer'\)/)
  assert.equal(table.match(/permission\('editor'\)/g)?.length, 2)
  assert.match(table, /permission\('manager'\)/)
  assert.match(table, /projectCatalog\.hasManagementRole\(project\.value, 'compliance', minimum\)/)
  assert.doesNotMatch(table, /hasEffectiveRole|_compdoc/)
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
    readFile(
      new URL('../src/features/compliance/composables/compdocController.ts', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/organization/api/organizationProjects.ts', import.meta.url),
      'utf8'
    )
  ])

  assert.match(store, /const requestedProject = state\.projectName/)
  assert.match(store, /const requestId = \+\+state\.listRequestId/)
  assert.match(
    store,
    /state\.projectName === requestedProject && state\.listRequestId === requestId/
  )
  assert.match(
    organizations,
    /if \(state\.project === requestedProject\) \{[\s\S]*state\.panels = getPaginatedResults<IPanel>\(data\)\.map[\s\S]*panel\.project_slug \|\| requestedProject/
  )
})

test('dashboard requests complete project analytics with cancellation support', async () => {
  const controller = new AbortController()
  let summary
  const captured = await captureRequest(async () => {
    summary = await fetchCompdocDashboard('project name', controller.signal)
  }, dashboardResponse())

  assert.equal(captured.url, 'projects/project%20name/compliance-documents/dashboard/')
  assert.notEqual(captured.signal, controller.signal)
  assert.equal(captured.signal.aborted, false)
  controller.abort()
  assert.equal(captured.signal.aborted, true)
  assert.deepEqual(summary, dashboardResponse())
})

test('dashboard isolates paginated table state and stale project responses', async () => {
  const [applicationHome, complianceHome, routes, menu, composable, dashboard] = await Promise.all([
    readFile(new URL('../src/app/pages/Home.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/features/compliance/pages/Home.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/app/router/routes.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/app/services/mainMenu.ts', import.meta.url), 'utf8'),
    readFile(
      new URL('../src/features/compliance/composables/dashboard.ts', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/compliance/components/ComplianceDashboard.vue', import.meta.url),
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
  assert.match(dashboard, /summary\.total/)
  assert.match(dashboard, /summary\.overdue/)
  assert.match(dashboard, /summary\.archived/)
  assert.match(dashboard, /summary\.status_counts/)
  assert.doesNotMatch(dashboard, /CompDocRiskDashboard|CompDocTrackingSummary|data_quality/)
})

test('adapts canonical workflow and review activity envelopes', async () => {
  let activity
  const captured = await captureRequest(
    async () => {
      activity = await fetchCompdocActivity('ozgur', 'document-id')
    },
    {
      results: [
        {
          type: 'workflow',
          at: '2026-08-01T10:00:00Z',
          data: {
            actor: 'operator',
            reason: 'Ready',
            previous_status: 'unknown',
            status: 'to_be_issued'
          }
        },
        {
          type: 'review',
          at: '2026-08-02T10:00:00Z',
          data: {
            kind: 'approval',
            requested_by_username: 'manager',
            request_note: 'Please approve',
            status: 'pending'
          }
        }
      ]
    }
  )

  assert.equal(captured.url, 'projects/ozgur/compliance-documents/document-id/activity/')
  assert.equal(activity[0].occurred_at, '2026-08-01T10:00:00Z')
  assert.equal(activity[1].type, 'approval')
  assert.equal(activity[1].actor, 'manager')
})

test('CompDoc charts use responsive modern Chart.js rendering paths', async () => {
  const [graph, status, timeline, legacyStore] = await Promise.all([
    readFile(new URL('../src/features/compliance/components/Graph.vue', import.meta.url), 'utf8'),
    readFile(
      new URL('../src/features/compliance/components/CompDocStatusDashboard.vue', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL(
        '../src/features/compliance/components/CompDocTimelineDashboard.vue',
        import.meta.url
      ),
      'utf8'
    ),
    readFile(new URL('../src/shared/stores/chartStore.js', import.meta.url), 'utf8')
  ])

  assert.match(graph, /display-directive="if"/)
  assert.match(graph, /buildClientCompdocSummary/)
  assert.match(status, /createStatusChartData/)
  assert.match(timeline, /createTimelineChartData/)
  assert.doesNotMatch(legacyStore, /Outlabels|\$compdocStore/)
})

test('exposes supported lifecycle resources and removes unsupported bulk/assignee calls', async () => {
  const [service, workspace, table, activity, transition] = await Promise.all([
    readFile(
      new URL('../src/features/compliance/api/compdocLifecycle.ts', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/compliance/components/CompDocWorkspace.vue', import.meta.url),
      'utf8'
    ),
    readFile(new URL('../src/features/compliance/pages/CompDocTable.vue', import.meta.url), 'utf8'),
    readFile(
      new URL('../src/features/compliance/components/CompDocActivity.vue', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/features/compliance/components/CompDocTransitionPanel.vue', import.meta.url),
      'utf8'
    )
  ])

  assert.match(service, /\/activity\//)
  assert.match(service, /\/transitions\//)
  assert.match(service, /\/reviews\//)
  assert.match(service, /\/work\//)
  assert.doesNotMatch(service, /bulk\/|assignees\//)
  assert.match(workspace, /CompDocWorkPanel/)
  assert.match(workspace, /CompDocReviewPanel/)
  assert.match(workspace, /CompDocActivity/)
  assert.doesNotMatch(table, /type: 'selection'|CompDocBulkActions/)
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
    project: 'project name',
    total: 4,
    archived: 1,
    overdue: 2,
    status_counts: { authority_review: 4 }
  }
}

function trackingResponse() {
  return {
    responsible_mode: 'automatic',
    responsible_person_ids: [],
    notification_enabled: false,
    notification_events: [],
    docproof_status: 'never_checked',
    docproof_issue: '',
    docproof_checked_at: null,
    notification_checked_at: null,
    updated_at: new Date(0).toISOString()
  }
}

function notificationPolicyRules() {
  return {
    overdue: { enabled: true },
    due_soon: { enabled: true },
    revision_available: { enabled: true }
  }
}
