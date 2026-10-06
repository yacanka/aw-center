import { expect, test, type Page } from '@playwright/test'

async function shell(page: Page, theme: string) {
  const record = {
    id: 'record-1',
    issue: 'CHN-42',
    title: 'Change document',
    active: true,
    version: 1,
    project_slugs: ['hys'],
    jira_issue_url: 'https://jira.example.test/browse/CHN-42'
  }
  const state = {
    records: [] as (typeof record)[],
    failStatus: false,
    failList: false,
    reminders: 0,
    checks: 0,
    importGate: null as Promise<void> | null,
    importStarted: false,
    role: 'operator',
    seed: record
  }
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.fallback()
    let body: unknown = { count: 0, next: null, previous: null, results: [] }
    if (path === '/api/session/')
      body = {
        state: 'authenticated',
        user: { id: 7, username: 'operator', permissions: [], is_superuser: false }
      }
    else if (path === '/api/users/preferences/') body = { theme, has_particles: false }
    else if (path === '/api/projects/')
      body = [
        {
          slug: 'hys',
          name: 'HYS',
          capabilities: ['dcc'],
          roles: { dcc: state.role, compliance: null, organization: null }
        }
      ]
    else if (path === '/api/integrations/jira/session/')
      body = { state: 'connected', expires_at: '2027-01-01T00:00:00Z' }
    else if (path === '/api/dcc/records/import/') {
      state.importStarted = true
      if (state.importGate) await state.importGate
      expect(route.request().postDataJSON()).toEqual({
        issue: 'https://jira.example.test/browse/CHN-42'
      })
      state.records = [{ ...record }]
      body = record
    } else if (path.endsWith('/status/')) {
      state.checks++
      if (state.failStatus)
        return route.fulfill({
          status: 502,
          json: { detail: 'JIRA unavailable. Retry.', code: 'DCC_WATCHER_JIRA_UNAVAILABLE' }
        })
      body = {
        ...record,
        status: 'In Progress',
        completed: false,
        checked_at: '2026-10-05T10:00:00Z',
        ecd_number: 'ECD-1',
        ecd_revision: 'A',
        dcc_number: 'DCC-1',
        subtasks: [
          {
            issue: 'CHN-43',
            title: 'Safety review',
            status: 'In Review',
            completed: false,
            jira_issue_url: 'https://jira.example.test/browse/CHN-43'
          },
          {
            issue: 'CHN-44',
            title: 'Software review',
            status: 'Done',
            completed: true,
            jira_issue_url: 'https://jira.example.test/browse/CHN-44'
          }
        ]
      }
    } else if (path === '/api/dcc/records/record-1/') {
      const values = route.request().postDataJSON()
      if (route.request().method() === 'DELETE') {
        expect(values).toEqual({ version: 2 })
        state.records = []
        return route.fulfill({ status: 204 })
      }
      expect(values.version).toBe(1)
      state.records[0] = { ...record, ...values, version: 2 }
      body = state.records[0]
    } else if (path === '/api/dcc/records/') {
      if (state.failList)
        return route.fulfill({
          status: 503,
          json: { detail: 'Temporarily unavailable.', code: 'UNAVAILABLE' }
        })
      const query = new URL(route.request().url()).searchParams
      const results = state.records.filter(
        (item) =>
          item.title.toLowerCase().includes((query.get('title') || '').toLowerCase()) &&
          item.issue.includes(query.get('issue') || '') &&
          (!query.has('active') || String(item.active) === query.get('active'))
      )
      body = { count: results.length, next: null, previous: null, results }
    } else if (path.endsWith('/reminders/')) {
      expect(route.request().postDataJSON()).toEqual({
        version: 2,
        ccb_no: 12,
        due_date: '2026-10-20'
      })
      expect(route.request().headers()['idempotency-key']).toBeTruthy()
      state.reminders++
      body = { id: 'delivery-1', status: 'pending' }
    } else if (path === '/api/dcc/assessments/')
      body = {
        document: { title: 'Change' },
        assessment: '1: Safety Panel Assessment: Major - Specialist review needed.'
      }
    else if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
    return route.fulfill({ json: body })
  })
  return state
}
for (const theme of ['light', 'dark']) {
  for (const width of [375, 1440]) {
    test(`Watcher workflow ${theme} ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const errors: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      const state = await shell(page, theme)
      await page.goto('/app/jira')
      await page.getByRole('button', { name: 'Add JIRA issue', exact: true }).click()
      const modal = page.locator('.n-modal:visible')
      await modal.locator('input').fill('https://jira.example.test/browse/CHN-42')
      await modal.getByRole('button', { name: 'Add issue', exact: true }).click()
      await expect(page.locator('.n-modal-mask')).toHaveCount(0)
      await expect(page.getByText('Progressing', { exact: true })).toBeVisible()
      await expect(page.getByText(/^Total: 1\./)).toBeVisible()
      await page.screenshot({ path: test.info().outputPath('watchlist.png'), fullPage: true })
      await page.getByRole('button', { name: 'Details', exact: true }).click()
      await expect(page.getByText('Safety review', { exact: true })).toBeVisible()
      await expect(page.getByText('In Review', { exact: true })).toBeVisible()
      await page.screenshot({ path: test.info().outputPath('watcher.png'), fullPage: true })
      await page.locator('.n-drawer-header__close').click()
      state.failStatus = true
      await page.getByRole('button', { name: 'More actions for CHN-42' }).click()
      await page.getByRole('menuitem', { name: 'Check status', exact: true }).click()
      await expect(page.getByText('JIRA unavailable. Retry.', { exact: true })).toBeVisible()
      await expect(page.getByText('Progressing', { exact: true })).toHaveCount(0)
      state.failStatus = false
      await page.getByRole('button', { name: 'More actions for CHN-42' }).click()
      await page.getByRole('menuitem', { name: 'Check status', exact: true }).click()
      await expect(page.getByText('Progressing', { exact: true })).toBeVisible()
      await page.getByRole('button', { name: 'More actions for CHN-42' }).click()
      await page.getByRole('menuitem', { name: 'Edit', exact: true }).click()
      await modal.getByRole('textbox', { name: 'Tracked issue title' }).fill('Updated title')
      await expect(modal.getByRole('switch', { name: 'Active tracking' })).toBeEnabled()
      await modal.getByRole('button', { name: 'Save', exact: true }).click()
      await expect(page.getByText('Updated title', { exact: true })).toBeVisible()
      await page.getByRole('button', { name: 'Send reminder', exact: true }).click()
      await modal.getByPlaceholder('CCB number').fill('12')
      await modal.locator('.n-date-picker input').fill('20.10.2026')
      await modal.locator('.n-date-picker input').press('Tab')
      await modal.getByRole('button', { name: 'Queue reminder', exact: true }).click()
      await expect.poll(() => state.reminders).toBe(1)
      await expect(page.locator('.n-modal-mask')).toHaveCount(0)
      await page.getByRole('button', { name: 'Assessment', exact: true }).click()
      await modal.locator('input[type=file]').setInputFiles({
        name: 'ecr.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.from('%PDF-1.4\n%%EOF')
      })
      await modal.getByRole('button', { name: 'Assess document', exact: true }).click()
      await expect(
        modal.getByText('1: Safety Panel Assessment: Major - Specialist review needed.', {
          exact: true
        })
      ).toBeVisible()
      await page.screenshot({ path: test.info().outputPath('assessment.png'), fullPage: true })
      await modal.locator('.n-card-header__close').click()
      await page.getByRole('button', { name: 'More actions for CHN-42' }).click()
      await page.getByRole('menuitem', { name: 'Remove', exact: true }).click()
      await page.locator('.n-dialog').getByRole('button', { name: 'Remove', exact: true }).click()
      await expect(page.getByText('Updated title', { exact: true })).toHaveCount(0)
      const dimensions = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth
      }))
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
      expect(errors).toEqual([])
    })
  }
}

test('filters, retries and keyboard details work in landscape with reduced motion', async ({
  page
}) => {
  await page.setViewportSize({ width: 820, height: 390 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const state = await shell(page, 'dark')
  state.records = [
    {
      ...state.seed,
      title:
        'A long engineering change title with multiple affected aircraft configurations and review disciplines'
    }
  ]
  await page.goto('/app/jira')
  await expect(page.getByText('Not checked yet', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Filters', exact: true }).click()
  await page.getByRole('textbox', { name: 'Filter by title' }).fill('unmatched')
  await page.getByRole('textbox', { name: 'Filter by title' }).press('Enter')
  await expect(page.getByText('No issues match these filters')).toBeVisible()
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
  await expect(page.getByText('Not checked yet', { exact: true })).toBeVisible()
  expect(state.checks).toBe(0)
  const details = page.getByRole('button', { name: 'Details', exact: true })
  await details.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByText('Software review', { exact: true })).toBeVisible()
  expect(state.checks).toBe(1)
  await page.getByRole('checkbox', { name: 'Outstanding only' }).check()
  await expect(page.getByText('Software review', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Safety review', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Close details' }).click()
  await page.getByRole('button', { name: 'More actions for CHN-42' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('menu', { name: 'Actions for CHN-42' })).toBeVisible()
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Enter')
  await expect.poll(() => state.checks).toBe(2)
  state.failList = true
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page.getByText('Could not load tracked issues')).toBeVisible()
  state.failList = false
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(page.getByText(/^Total: 1\./)).toBeVisible()
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth
  }))
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
})

test('viewers can inspect records without mutation controls', async ({ page }) => {
  const state = await shell(page, 'light')
  state.role = 'viewer'
  state.records = [state.seed]
  await page.goto('/app/jira')
  await expect(page.getByRole('button', { name: 'Add JIRA issue', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Send reminder', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Details', exact: true }).click()
  await expect(page.getByText('Safety review', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Close details' }).click()
  await page.getByRole('button', { name: 'More actions for CHN-42' }).click()
  await expect(page.getByRole('menuitem', { name: 'Edit', exact: true })).toHaveAttribute(
    'aria-disabled',
    'true'
  )
  await expect(page.getByRole('menuitem', { name: 'Remove', exact: true })).toHaveAttribute(
    'aria-disabled',
    'true'
  )
})

test('Escape cannot dismiss an import while it is being saved', async ({ page }) => {
  const state = await shell(page, 'light')
  let release = () => {}
  state.importGate = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.goto('/app/jira')
  await page.getByRole('button', { name: 'Add JIRA issue', exact: true }).click()
  const modal = page.locator('.n-modal:visible')
  await modal
    .getByRole('textbox', { name: 'JIRA issue URL or key' })
    .fill('https://jira.example.test/browse/CHN-42')
  await modal.getByRole('button', { name: 'Add issue', exact: true }).click()
  await expect.poll(() => state.importStarted).toBe(true)
  await page.keyboard.press('Escape')
  await expect(modal).toBeVisible()
  await expect(modal.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
  release()
  await expect(modal).toHaveCount(0)
  await expect(page.getByText('Progressing', { exact: true })).toBeVisible()
})
