import { expect, test, type Page } from '@playwright/test'

const record = {
  id: 'record-1',
  issue: 'CHN-42',
  title: 'Change document',
  owner: 7,
  assigned_users: [],
  project_slugs: ['hys'],
  version: 1,
  created_at: '2026-10-05T10:00:00Z',
  updated_at: '2026-10-05T10:00:00Z',
  jira_issue_url: 'https://jira.example.test/browse/CHN-42'
}
const availableFields = [
  { id: 'customfield_45000', label: 'ECD number', value: 'ECD-1' },
  { id: 'customfield_45001', label: 'Revision', value: 'A' },
  { id: 'customfield_45002', label: 'DCC number', value: 'DCC-1' },
  { id: 'priority', label: 'Priority', value: 'High' }
]

for (const theme of ['light', 'dark'] as const) {
  for (const width of [375, 1440]) {
    test(`Watcher settings save and reload in ${theme} at ${width}px`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 900 })
      const state = await shell(page, theme)
      await page.goto('/app/settings')
      const settings = page.getByRole('region', { name: 'JIRA Watcher', exact: true })
      await expect(settings).toBeVisible()
      await expect(settings).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(24, 24, 28)' : 'rgb(255, 255, 255)'
      )
      await expect.poll(() => state.projects).toEqual(['hys'])
      const save = settings.getByRole('button', { name: 'Save detail fields', exact: true })
      await expect(save).toBeDisabled()
      await loadIssue(page)
      const fields = settings.locator('.n-select[aria-label="Watcher detail fields"]')
      const input = fields.getByRole('textbox', { name: 'Watcher detail fields' })
      await fields.locator('.n-base-selection').click()
      await input.focus()
      await input.press('Backspace')
      await input.press('Backspace')
      await input.press('Backspace')
      await input.fill('Priority')
      await input.press('Enter')
      await input.press('Escape')
      await expect(fields.locator('.n-tag')).toHaveCount(1)
      await expect(fields.locator('.n-tag')).toHaveText('Priority')
      await save.click()
      await expect(settings.getByRole('alert')).toContainText('Detail fields saved')
      expect(state.patches).toEqual([{ project_slug: 'hys', detail_field_ids: ['priority'] }])
      expect(state.preferences.outstanding_only).toBe(true)
      await page.screenshot({
        path: info.outputPath('watcher-settings.png'),
        animations: 'disabled'
      })

      await page.reload()
      await loadIssue(page)
      await expect(fields.locator('.n-tag')).toHaveCount(1)
      await expect(fields.locator('.n-tag')).toHaveText('Priority')
      await fields.locator('.n-base-selection').click()
      await input.focus()
      await input.press('Backspace')
      await input.press('Escape')
      await expect(fields.locator('.n-tag')).toHaveCount(0)
      await save.click()
      await expect(settings.getByRole('alert')).toContainText('Detail fields saved')
      expect(state.patches.at(-1)).toEqual({ project_slug: 'hys', detail_field_ids: [] })
      await page.reload()
      await loadIssue(page)
      await expect(fields.locator('.n-tag')).toHaveCount(0)

      const dimensions = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth
      }))
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
      const bounds = await save.boundingBox()
      expect(bounds).not.toBeNull()
      expect(bounds!.x).toBeGreaterThanOrEqual(0)
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width)
      expect(state.errors).toEqual([])
    })
  }
}

test('preference loading failure disables saving and can be retried', async ({ page }) => {
  const state = await shell(page, 'light')
  state.failPreferences = true
  await page.goto('/app/settings')
  const settings = page.getByRole('region', { name: 'JIRA Watcher', exact: true })
  await expect(settings.getByRole('alert')).toContainText('Settings temporarily unavailable.')
  await expect(settings.getByRole('button', { name: 'Save detail fields' })).toBeDisabled()
  expect(state.projects).toEqual([])
  state.failPreferences = false
  await settings.getByRole('button', { name: 'Retry settings' }).click()
  await loadIssue(page)
  await expect(settings.getByRole('button', { name: 'Save detail fields' })).toBeEnabled()
  expect(state.patches).toEqual([])
})

test('status loading failure preserves settings and prevents an incomplete save', async ({
  page
}) => {
  const state = await shell(page, 'dark')
  state.failStatus = true
  await page.goto('/app/settings')
  const settings = page.getByRole('region', { name: 'JIRA Watcher', exact: true })
  await chooseIssue(page)
  await expect(settings.getByRole('alert')).toContainText('JIRA unavailable. Retry.')
  await expect(settings.getByRole('button', { name: 'Save detail fields' })).toBeDisabled()
  await expect(settings.locator('.n-select[aria-label="Watcher detail fields"]')).toHaveCount(0)
  expect(state.preferences.detail_fields).toEqual({})
  expect(state.patches).toEqual([])
  state.failStatus = false
  await settings.getByRole('button', { name: 'Retry loading fields' }).click()
  await expect(settings.locator('.n-select[aria-label="Watcher detail fields"]')).toBeVisible()
  await expect(settings.getByRole('button', { name: 'Save detail fields' })).toBeEnabled()
})

test('project selection scopes records and preserves the other project preferences', async ({
  page
}) => {
  const state = await shell(page, 'light')
  state.preferences.detail_fields = { hys: ['priority'], aesa: ['customfield_45001'] }
  await page.goto('/app/settings')
  const settings = page.getByRole('region', { name: 'JIRA Watcher', exact: true })
  await loadIssue(page)
  const fields = settings.locator('.n-select[aria-label="Watcher detail fields"]')
  await expect(fields.locator('.n-tag')).toHaveText('Priority')
  await settings
    .locator('.n-select[aria-label="Watcher settings project"] .n-base-selection')
    .click()
  await page
    .locator('.n-base-select-option')
    .filter({ hasText: /^AESA$/ })
    .click()
  await expect.poll(() => state.projects.at(-1)).toBe('aesa')
  await chooseIssue(page, 'CHN-84')
  await expect(fields.locator('.n-tag')).toHaveText('Revision')
  await fields.locator('.n-base-selection').click()
  const input = fields.getByRole('textbox', { name: 'Watcher detail fields' })
  await input.press('Backspace')
  await input.press('Escape')
  await settings.getByRole('button', { name: 'Save detail fields' }).click()
  await expect.poll(() => state.patches).toEqual([{ project_slug: 'aesa', detail_field_ids: [] }])
  expect(state.preferences.detail_fields).toEqual({ hys: ['priority'], aesa: [] })
})

async function chooseIssue(page: Page, issue = 'CHN-42'): Promise<void> {
  const select = page.locator('.n-select[aria-label="Tracked issue for detail fields"]')
  await expect(select.locator('.n-base-selection')).not.toHaveClass(/disabled/)
  await select.locator('.n-base-selection').click()
  const input = select.getByRole('textbox', { name: 'Tracked issue for detail fields' })
  await input.fill(issue)
  await input.press('ArrowDown')
  await input.press('Enter')
}

async function loadIssue(page: Page): Promise<void> {
  await chooseIssue(page)
  await expect(page.locator('.n-select[aria-label="Watcher detail fields"]')).toBeVisible()
}

async function shell(page: Page, theme: 'light' | 'dark') {
  const state = {
    preferences: { outstanding_only: true, detail_fields: {} as Record<string, string[]> },
    patches: [] as { project_slug: string; detail_field_ids: string[] }[],
    projects: [] as string[],
    failPreferences: false,
    failStatus: false,
    errors: [] as string[]
  }
  page.on('pageerror', (error) => state.errors.push(error.message))
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    if (!path.startsWith('/api/')) return route.fallback()
    if (path === '/api/session/') {
      return route.fulfill({
        headers: { 'set-cookie': 'csrftoken=watcher-settings-fixture; Path=/; SameSite=Lax' },
        json: {
          state: 'authenticated',
          user: {
            id: 7,
            username: 'settings-operator',
            first_name: 'Settings',
            last_name: 'Operator',
            email: 'settings@example.test',
            is_active: true,
            is_staff: false,
            is_superuser: false,
            permissions: [],
            group_details: []
          }
        }
      })
    }
    if (path === '/api/users/preferences/') {
      return route.fulfill({ json: { theme, has_particles: false } })
    }
    if (path === '/api/projects/') {
      return route.fulfill({
        json: [
          {
            slug: 'hys',
            name: 'HYS',
            capabilities: ['jira'],
            roles: { jira: 'operator', compliance: null, organization: null }
          },
          {
            slug: 'aesa',
            name: 'AESA',
            capabilities: ['jira'],
            roles: { jira: 'operator', compliance: null, organization: null }
          }
        ]
      })
    }
    if (path === '/api/integrations/jira/watcher/preferences/') {
      if (state.failPreferences) {
        return route.fulfill({
          status: 503,
          json: { detail: 'Settings temporarily unavailable.', code: 'UNAVAILABLE' }
        })
      }
      if (request.method() === 'PATCH') {
        expect(request.headers()['x-csrftoken']).toBe('watcher-settings-fixture')
        const patch = request.postDataJSON()
        state.patches.push(patch)
        state.preferences.detail_fields[patch.project_slug] = patch.detail_field_ids
      }
      return route.fulfill({ json: state.preferences })
    }
    if (path === '/api/integrations/jira/records/') {
      const project = url.searchParams.get('project_slug')
      state.projects.push(project || '')
      const scopedRecord =
        project === 'aesa'
          ? { ...record, id: 'record-2', issue: 'CHN-84', project_slugs: ['aesa'] }
          : record
      return route.fulfill({
        json: { count: 1, results: [scopedRecord], next: null, previous: null }
      })
    }
    if (/^\/api\/integrations\/jira\/records\/record-[12]\/status\/$/.test(path)) {
      if (state.failStatus) {
        return route.fulfill({
          status: 502,
          json: { detail: 'JIRA unavailable. Retry.', code: 'DCC_WATCHER_JIRA_UNAVAILABLE' }
        })
      }
      return route.fulfill({
        json: {
          ...record,
          ...(path.includes('record-2')
            ? { id: 'record-2', issue: 'CHN-84', project_slugs: ['aesa'] }
            : {}),
          status: 'In Progress',
          completed: false,
          issue_completed: false,
          record_version: 1,
          detail_fields: availableFields,
          checked_at: '2026-10-05T10:00:00Z',
          ecd_number: 'ECD-1',
          ecd_revision: 'A',
          dcc_number: 'DCC-1',
          subtasks: []
        }
      })
    }
    if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
    return route.fulfill({ json: { count: 0, results: [], next: null, previous: null } })
  })
  return state
}
