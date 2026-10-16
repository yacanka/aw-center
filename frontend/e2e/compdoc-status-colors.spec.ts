import { expect, test, type Locator } from '@playwright/test'

const statuses = [
  'to_be_issued',
  'airworthiness_review',
  'authority_review',
  'authority_approved',
  'to_be_updated',
  'to_be_re-submitted',
  'unknown',
  'delayed'
]
const documents = statuses.map((status, index) => ({
  id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
  name: `Color document ${index}`,
  status,
  version: 1,
  cover_page: { number: `CP-${index}`, issue: 'A', version: 1 },
  number: `TD-${index}`,
  issue: 'B',
  target_date: null,
  revised_target_date: null,
  release_date: null,
  signature_panel: [],
  requirements: [],
  panel: null
}))

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`status tags stay readable in ${theme} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const errors: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname
        if (!path.startsWith('/api/')) return route.fallback()
        let body: unknown = { count: 0, results: [], next: null, previous: null }
        if (path === '/api/session/')
          body = {
            state: 'authenticated',
            user: {
              id: 1,
              username: 'color-test',
              is_active: true,
              is_staff: false,
              is_superuser: false
            }
          }
        else if (path === '/api/users/preferences/') body = { theme, has_particles: false }
        else if (path === '/api/projects/')
          body = [
            {
              slug: 'ozgur',
              name: 'OZGUR',
              capabilities: ['compliance'],
              roles: { compliance: 'manager', jira: null, organization: null }
            }
          ]
        else if (path.endsWith('/fields/'))
          body = {
            schema_version: 4,
            project: 'ozgur',
            fields: ['name', 'status'].map((key) => ({
              key,
              label: key,
              required: key === 'name',
              read_only: key === 'status',
              width: 180,
              default_visible: true,
              choices: [],
              option_source: null,
              filter_kind: 'text',
              sortable: true
            }))
          }
        else if (path.endsWith('/statuses/')) body = []
        else if (path.endsWith('/numbering-options/'))
          body = {
            provider: 'numarator',
            available: false,
            supports: [],
            formats: []
          }
        else if (path.endsWith('/compliance-documents/'))
          body = {
            count: documents.length,
            results: documents,
            next: null,
            previous: null
          }
        else if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
        else {
          const document = documents.find((item) => path.endsWith(`/${item.id}/`))
          if (document) body = document
        }
        return route.fulfill({ json: body })
      })
      await page.goto('/app/compdocs/ozgur')
      const tableTags = page.locator('.n-data-table-td .n-tag')
      await expect(tableTags).toHaveCount(statuses.length)
      for (const tag of await tableTags.all()) await assertContrast(tag)
      await page.getByText('Color document 1', { exact: true }).dblclick()
      const drawer = page.locator('.n-drawer-content')
      await expect(drawer).toBeVisible()
      await assertContrast(drawer.locator('.workspace-heading .n-tag'))
      await page.screenshot({
        path: `test-results/status-drawer-${theme}-${width}.png`,
        animations: 'disabled'
      })
      await drawer.getByRole('button', { name: 'Edit', exact: true }).click()
      const dialog = page.getByRole('dialog')
      const tag = dialog.locator('form .n-tag').filter({ hasText: 'Aw Review' })
      await tag.scrollIntoViewIfNeeded()
      await expect(tag).toBeVisible()
      await assertContrast(tag)
      const dimensions = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth
      }))
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
      expect(errors).toEqual([])
      await page.screenshot({
        path: `test-results/status-form-${theme}-${width}.png`,
        animations: 'disabled'
      })
    })
  }
}

async function assertContrast(tag: Locator) {
  const ratio = await tag.evaluate((node) => {
    const css = getComputedStyle(node)
    function luminance(color: string) {
      const channels = color
        .match(/[\d.]+/g)!
        .slice(0, 3)
        .map(Number)
        .map((value) => value / 255)
      const linear = channels.map((value) =>
        value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
      )
      return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
    }
    const values = [luminance(css.color), luminance(css.backgroundColor)].sort((a, b) => b - a)
    return (values[0] + 0.05) / (values[1] + 0.05)
  })
  expect(ratio).toBeGreaterThanOrEqual(4.5)
}
