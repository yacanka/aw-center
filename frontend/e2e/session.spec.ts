import { expect, test, type Page, type Route } from '@playwright/test'

const unresolvedComponents = new WeakMap<Page, string[]>()
const pageErrors = new WeakMap<Page, string[]>()

test.beforeEach(async ({ page }) => {
  const warnings: string[] = []
  const errors: string[] = []
  unresolvedComponents.set(page, warnings)
  pageErrors.set(page, errors)
  page.on('console', (message) => {
    if (message.text().includes('Failed to resolve component')) warnings.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
})

test.afterEach(async ({ page }) => {
  expect(unresolvedComponents.get(page) || []).toEqual([])
  expect(pageErrors.get(page) || []).toEqual([])
})

const anonymousSession = { state: 'anonymous', user: null }
const authenticatedSession = {
  state: 'authenticated',
  user: {
    id: 7,
    username: 'operator',
    email: 'operator@example.test',
    first_name: 'Test',
    last_name: 'Operator',
    is_staff: false,
    is_superuser: false,
    permissions: []
  }
}

test('protected deep link waits for session bootstrap and redirects anonymously', async ({
  page
}) => {
  await routeSessionBootstrap(page)

  await page.goto('/app/jobs')

  await expect(page).toHaveURL(/\/app\/login\?redirect=\/jobs$/)
  await expect(page.getByRole('button', { name: 'Login' })).toBeVisible()
})

test('password reset capability is consumed from the fragment and immediately scrubbed', async ({
  page
}) => {
  await routeSessionBootstrap(page)

  await page.goto('/app/login#uid=MQ&token=client-only-capability')

  await expect(page).toHaveURL(/\/app\/login$/)
  await expect(page.getByText('Set new password')).toBeVisible()
  expect(await page.evaluate(() => window.location.hash)).toBe('')
})

test('login sends Django CSRF and enters the protected shell', async ({ page }) => {
  let submittedCsrf = ''
  let authenticated = false
  await page.route('**/api/session/', async (route) => {
    if (route.request().method() === 'GET') {
      return json(route, authenticated ? authenticatedSession : anonymousSession, {
        'set-cookie': 'csrftoken=playwright-csrf; Path=/; SameSite=Lax'
      })
    }
    if (route.request().method() !== 'POST') return route.fallback()
    submittedCsrf = route.request().headers()['x-csrftoken'] || ''
    authenticated = true
    await json(route, authenticatedSession)
  })
  await page.route('**/api/users/preferences/', (route) => json(route, {}))
  await page.route('**/api/projects/**', (route) => json(route, []))
  await page.route('**/api/releases/**', (route) => route.fulfill({ status: 204 }))
  await page.route('**/api/jobs/**', (route) => {
    const response = new URL(route.request().url()).pathname.endsWith('/system/')
      ? { available: false, active_workers: 0, counts: {} }
      : { count: 0, next: null, previous: null, results: [] }
    return json(route, response)
  })

  await page.goto('/app/login?redirect=/jobs')
  await page.getByPlaceholder('Enter your registration number').fill('operator')
  await page.getByPlaceholder('Enter your password').fill('runtime-only-password')
  await page.getByRole('button', { name: 'Login' }).click()

  await expect(page).toHaveURL(/\/app\/jobs$/)
  expect(submittedCsrf).toBe('playwright-csrf')
})

test('presentation upload queues one idempotent job and downloads its private result', async ({
  page
}) => {
  await routeAuthenticatedShell(page)
  let artifactRequested = false
  let uploadQueued = false
  await page.route('**/api/tools/presentations/presentations/**', async (route) => {
    const request = route.request()
    if (request.method() === 'POST' && request.url().endsWith('/upload/')) {
      expect(request.headers()['idempotency-key']).toBeTruthy()
      uploadQueued = true
      return json(route, completedJob())
    }
    return json(route, { count: 0, next: null, previous: null, results: [] })
  })
  await page.route('**/api/jobs/job-presentation/download/', async (route) => {
    artifactRequested = true
    await route.fulfill({
      status: 200,
      contentType: 'application/octet-stream',
      body: 'verified-artifact'
    })
  })

  await page.goto('/app/pptxGallery')
  await page.locator('input[type="file"]').setInputFiles({
    name: 'reviewed.pptx',
    mimeType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    buffer: Buffer.from('mocked-presentation')
  })

  await expect.poll(() => uploadQueued).toBe(true)
  await page.getByRole('button', { name: 'Download result' }).click()
  await expect.poll(() => artifactRequested).toBe(true)
})

test('PoC Linker queues a durable preview and renders the verified result', async ({ page }) => {
  await routeAuthenticatedShell(page)
  await page.route('**/api/integrations/doors/status/', (route) =>
    json(route, {
      configured: true,
      available: true,
      active_runners: 1,
      transport: 'loopback_token'
    })
  )

  let queuedInput: unknown = null
  await page.route('**/api/integrations/doors/requirement-link-jobs/', async (route) => {
    expect(route.request().headers()['idempotency-key']).toBeTruthy()
    queuedInput = route.request().postDataJSON()
    await json(route, completedLinkerJob())
  })
  await page.route('**/api/jobs/job-poc-linker/download/', (route) =>
    json(route, {
      type: 'doors_requirement_linker',
      schema_version: 1,
      mode: 'preview',
      direction: 'ref2tar',
      summary: {
        reference_objects: 2,
        groups: 1,
        candidates: 2,
        matched_targets: 1,
        missing_targets: 0,
        created_links: 0,
        existing_links: 0
      },
      groups: [{ poc: 'POC-001', requirements: ['REQ-1', 'REQ-2'], target_found: true }],
      missing_targets: []
    })
  )

  await page.goto('/app/doors/poclinker')
  await page.getByPlaceholder('/Project/Reference Module').fill('/Project/Reference')
  await page.getByPlaceholder('/Project/Target Module').fill('/Project/Target')
  await page.getByPlaceholder('/Project/Links').fill('/Project/Links')
  await page.getByPlaceholder('PoC List').fill('PoC List')
  await page.getByPlaceholder('Requirement').fill('Requirement')
  await page.getByPlaceholder('PoC Info').fill('PoC Info')
  await page.getByRole('button', { name: 'Queue preview' }).click()

  await expect
    .poll(() => queuedInput)
    .toEqual({
      ref_module_name: '/Project/Reference',
      target_module_name: '/Project/Target',
      link_module_name: '/Project/Links',
      ref_attr_poc: 'PoC List',
      ref_attr_req: 'Requirement',
      target_attr_poc: 'PoC Info',
      start_index: 0,
      text_length: -1,
      direction: 'ref2tar',
      activeness: false
    })
  await expect(page.getByText('POC-001', { exact: true })).toBeVisible()
  await page.getByText('POC-001', { exact: true }).click()
  await expect(page.getByText('REQ-1', { exact: true })).toBeVisible()
  await expect(page.getByText('Target found', { exact: true })).toBeVisible()
})

test('stale compliance import refreshes the reviewed preview on VERSION_CONFLICT', async ({
  page
}) => {
  await routeAuthenticatedShell(page)
  await page.route('**/api/projects/', (route) =>
    json(route, [
      {
        slug: 'aesa',
        name: 'AESA',
        capabilities: ['compliance'],
        roles: { compliance: 'editor', organization: null, dcc: null }
      }
    ])
  )
  await page.route('**/api/projects/aesa/organization/panels/**', (route) =>
    json(route, { count: 0, next: null, previous: null, results: [] })
  )
  await page.route('**/api/projects/aesa/compliance-documents/fields/', (route) =>
    json(route, {
      schema_version: 1,
      project: 'aesa',
      fields: [{ key: 'name', label: 'Name', required: true, read_only: false }]
    })
  )
  await page.route('**/api/projects/aesa/compliance-documents/?*', (route) =>
    json(route, { count: 0, next: null, previous: null, results: [] })
  )
  let previewCount = 0
  await page.route('**/api/projects/aesa/compliance-documents/imports/**', async (route) => {
    if (route.request().url().endsWith('/confirm/')) {
      return route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'The reviewed records changed.',
          code: 'VERSION_CONFLICT'
        })
      })
    }
    previewCount += 1
    return json(route, importPreview(`preview-${previewCount}`, previewCount))
  })

  await page.goto('/app/compdocs/aesa')
  await page.getByRole('button', { name: 'Import Excel', exact: true }).click()
  await page.locator('input[type="file"]').setInputFiles({
    name: 'compliance.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: Buffer.from('mocked-workbook')
  })
  await expect(page.getByText('Confirm Excel Import')).toBeVisible()
  await page.getByRole('button', { name: 'Confirm Import' }).click()

  await expect(
    page.getByText('The preview was refreshed; review it again.', { exact: false })
  ).toBeVisible()
  expect(previewCount).toBe(2)
})

test('reconciled ECR publication resumes with a new idempotent durable attempt', async ({
  page
}) => {
  await routeAuthenticatedShell(page)
  await page.route('**/api/projects/', (route) =>
    json(route, [
      {
        slug: 'aesa',
        name: 'AESA',
        capabilities: ['dcc'],
        roles: { compliance: null, organization: null, dcc: 'publisher' }
      }
    ])
  )
  await page.route('**/api/integrations/jira/session/', (route) =>
    json(route, {
      state: 'connected',
      expires_at: '2026-08-18T01:00:00Z'
    })
  )

  let workflow = ecrWorkflow()
  let resumeRequested = false
  await page.route('**/api/workflows/ecr/**', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    if (request.method() === 'POST' && pathname.endsWith('/resume/')) {
      expect(request.headers()['idempotency-key']).toBeTruthy()
      expect(request.postDataJSON()).toEqual({ version: 11 })
      resumeRequested = true
      workflow = {
        ...workflow,
        status: 'publishing',
        version: 12,
        publication: {
          ...workflow.publication,
          job_id: 'job-ecr-resume',
          job_status: 'queued'
        },
        allowed_actions: {
          approve: false,
          reject: false,
          publish: false,
          resume: false,
          cancel: true
        }
      }
      return json(route, workflow)
    }
    if (pathname.endsWith('/api/workflows/ecr/')) {
      return json(route, { count: 1, next: null, previous: null, results: [workflow] })
    }
    return json(route, { ...workflow, events: [] })
  })

  await page.goto('/app/task/ecr?ecr_workflow=ecr-workflow-1')
  await expect(page.getByText('Automatic retry is disabled.', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'Resume publication' }).click()
  await page.getByRole('button', { name: 'Confirm' }).click()

  await expect.poll(() => resumeRequested).toBe(true)
  await expect(page.getByText('Durable job status: queued')).toBeVisible()
})

async function routeSessionBootstrap(page: Page): Promise<void> {
  await page.route('**/api/session/', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'set-cookie': 'csrftoken=playwright-csrf; Path=/; SameSite=Lax' },
      body: JSON.stringify(anonymousSession)
    })
  })
}

async function routeAuthenticatedShell(page: Page): Promise<void> {
  await page.route('**/api/session/', (route) => json(route, authenticatedSession))
  await page.route('**/api/users/preferences/', (route) => json(route, {}))
  await page.route('**/api/releases/**', (route) => route.fulfill({ status: 204 }))
  await page.route('**/api/projects/', (route) => json(route, []))
}

function completedJob() {
  return {
    id: 'job-presentation',
    kind: 'presentations.convert',
    title: 'Convert presentation',
    status: 'succeeded',
    progress: 100,
    message: 'Presentation converted.',
    error_code: '',
    input_name: 'reviewed.pptx',
    output_name: 'reviewed.zip',
    result_summary: { presentation_id: 'presentation-1' },
    attempt: 1,
    max_attempts: 1,
    source_job: null,
    workflow_run: null,
    workflow_step: null,
    request_id: 'request-presentation',
    created_at: '2026-08-18T00:00:00Z',
    started_at: '2026-08-18T00:00:01Z',
    completed_at: '2026-08-18T00:00:02Z',
    confirmation_expires_at: null,
    updated_at: '2026-08-18T00:00:02Z',
    can_cancel: false,
    download_url: '/api/jobs/job-presentation/download/',
    recovery_hint: '',
    jira_draft: null
  }
}

function completedLinkerJob() {
  return {
    ...completedJob(),
    id: 'job-poc-linker',
    kind: 'doors.link_requirements',
    title: 'Preview requirement links',
    message: 'Requirement link preview completed.',
    input_name: 'requirement-link-input.json',
    output_name: 'requirement-link-result.json',
    result_summary: {},
    request_id: 'request-poc-linker',
    download_url: '/api/jobs/job-poc-linker/download/'
  }
}

function importPreview(confirmationToken: string, updatedCount: number) {
  return {
    header_row: 1,
    mapped_columns: [{ source: 'Name', target: 'name' }],
    unmapped_columns: [],
    missing_columns: [],
    invalid_documents: [],
    created_count: 0,
    updated_count: updatedCount,
    unchanged_count: 0,
    rejected_count: 0,
    confirmation_token: confirmationToken,
    database_state_protected: true
  }
}

function ecrWorkflow() {
  return {
    id: 'ecr-workflow-1',
    status: 'reconciliation_required',
    version: 11,
    project_slugs: ['aesa'],
    snapshot: {
      ecr_number: 'ECR-2026-001',
      title: 'Reviewed propulsion change',
      project: 'AESA',
      change_class: 'Class I',
      change_type: 'Design',
      effectivity: 'All',
      track_type: 'CRB',
      record_of_change: 'Controlled change',
      requestor: 'Engineering',
      originator: 'Systems',
      ata: '71',
      subata: '',
      initiator: 'Test Operator',
      justification: 'Verified requirement',
      proposed_solution: 'Reviewed implementation',
      nonimplementation_consequence: 'Schedule impact',
      impacted_groups: 'Engineering'
    },
    approval: {
      project_key: 'AWC',
      extra_fields: {},
      subtasks: [],
      approved_at: '2026-08-18T00:00:00Z',
      rejected_at: null
    },
    publication: {
      job_id: 'job-ecr-previous',
      job_status: 'reconciliation_required',
      jira_issue_key: '',
      attachment_confirmed: false,
      subtasks_confirmed: 0,
      subtasks_total: 0,
      published_at: null,
      last_error: {
        code: 'ECR_RECONCILIATION_REQUIRED',
        detail: 'The previous external result is uncertain.'
      }
    },
    allowed_actions: {
      approve: false,
      reject: false,
      publish: false,
      resume: true,
      cancel: false
    },
    created_at: '2026-08-18T00:00:00Z',
    updated_at: '2026-08-18T00:05:00Z'
  }
}

async function json(
  route: Route,
  body: unknown,
  headers: Record<string, string> = {}
): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers,
    body: JSON.stringify(body)
  })
}
