import { expect, test, type Page } from '@playwright/test'

const options = {
  preset: 'balanced',
  equal_ratio: 0.92,
  weak_equal_ratio: 0.7,
  output_type: 'excel'
}
const table = {
  sheets: [{ name: 'Data', headers: [{ row: 1, labels: ['ID', 'Description'] }] }],
  selected: { sheet: 'Data', header_row: 1 },
  columns: ['ID', 'Description'],
  preview: [['1', 'A document requirement']],
  row_count: 1
}
const inspection = {
  first: table,
  second: table,
  options,
  selection: {
    first: table.selected,
    second: table.selected,
    columns: [
      [0, 0],
      [1, 1]
    ],
    matching: { mode: 'keys', keys: [0] }
  },
  matching: {
    method: 'keys',
    requires_input: false,
    reason: 'Non-empty, unique identity columns.',
    keys: [0]
  },
  warnings: []
}
const baseJob = {
  id: 'inspection',
  title: 'Inspect comparison tables',
  kind: 'comparison.inspect',
  status: 'succeeded',
  progress: 100,
  message: 'Table inspection ready.',
  attempt: 1,
  max_attempts: 3,
  can_cancel: false,
  download_url: null,
  result_summary: {},
  recovery_hint: ''
}

async function mockApi(page: Page, theme: string) {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.fallback()
    if (path === '/api/session/')
      return route.fulfill({
        json: {
          state: 'authenticated',
          user: {
            id: 7,
            username: 'compare-test',
            is_active: true,
            is_staff: true,
            is_superuser: true,
            permissions: [],
            group_details: [],
            preferences: { theme, has_particles: false }
          }
        }
      })
    if (path === '/api/users/preferences/')
      return route.fulfill({ json: { theme, has_particles: false } })
    if (path === '/api/projects/') return route.fulfill({ json: [] })
    if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
    if (path.endsWith('/compare/presets/'))
      return route.fulfill({
        json: {
          presets: [
            {
              id: 'balanced',
              label: 'Balanced',
              description: 'Everyday revision comparisons.',
              equal_ratio: 0.92,
              weak_equal_ratio: 0.7
            }
          ],
          default: 'balanced'
        }
      })
    if (path.endsWith('/compare/inspections/')) return route.fulfill({ json: baseJob })
    if (path.endsWith('/compare/inspections/inspection/'))
      return route.fulfill({ json: inspection })
    if (path.endsWith('/compare/jobs/'))
      return route.fulfill({
        json: {
          ...baseJob,
          id: 'report',
          kind: 'comparison.compare',
          title: 'Compare files',
          download_url: '/api/jobs/report/download/'
        }
      })
    if (path.endsWith('/jobs/report/download/'))
      return route.fulfill({ contentType: 'application/octet-stream', body: 'report-fixture' })
    return route.fulfill({ json: { count: 0, results: [], next: null, previous: null } })
  })
}

for (const theme of ['light', 'dark']) {
  for (const width of [390, 1440]) {
    test(`unified Excel flow and theme ${theme} at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 950 })
      await page.emulateMedia({ colorScheme: theme as 'light' | 'dark' })
      const errors: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      await mockApi(page, theme)
      await page.goto('/app/compare/excel')
      await expect(page).toHaveURL(/\/app\/compare$/)
      const upload = page.locator('input[type=file]')
      await upload.nth(0).setInputFiles({
        name: 'old.xlsx',
        mimeType: 'application/octet-stream',
        buffer: Buffer.from('old')
      })
      await upload.nth(1).setInputFiles({
        name: 'new.xlsx',
        mimeType: 'application/octet-stream',
        buffer: Buffer.from('new')
      })
      await expect(page.getByRole('button', { name: 'Compare and download' })).toBeDisabled()
      await page.getByRole('button', { name: 'Inspect tables', exact: true }).click()
      await expect(page.getByText('Suggested identity: ID.', { exact: false })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Compare and download' })).toBeEnabled()
      await page.getByText('Column mapping', { exact: true }).click()
      await expect(page.getByText('Map renamed columns here.', { exact: false })).toBeVisible()
      const sizes = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth
      }))
      expect(sizes.scroll).toBeLessThanOrEqual(sizes.width + 1)
      await page.screenshot({ path: `test-results/compare-${theme}-${width}.png`, fullPage: true })
      const download = page.waitForEvent('download')
      await page.getByRole('button', { name: 'Compare and download' }).click()
      await download
      expect(errors).toEqual([])
    })
  }
}

test('mixed files block compare and old Word/PDF links redirect', async ({ page }) => {
  await mockApi(page, 'light')
  for (const path of ['word', 'pdf']) {
    await page.goto(`/app/compare/${path}`)
    await expect(page).toHaveURL(/\/app\/compare$/)
  }
  await page
    .locator('input[type=file]')
    .nth(0)
    .setInputFiles({
      name: 'a.docx',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('a')
    })
  await page
    .locator('input[type=file]')
    .nth(1)
    .setInputFiles({ name: 'b.pdf', mimeType: 'application/pdf', buffer: Buffer.from('b') })
  await expect(page.getByText('Both files must be the same type:', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Compare and download' })).toBeDisabled()
})
