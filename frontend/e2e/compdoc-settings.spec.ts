import { expect, test } from '@playwright/test'

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`compliance settings save and inherit ${theme} theme at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.emulateMedia({ colorScheme: theme })
      await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname
        if (!path.startsWith('/api/')) return route.fallback()
        let body: unknown = { count: 0, results: [], next: null, previous: null }
        if (path === '/api/session/')
          body = {
            state: 'authenticated',
            user: {
              id: 1,
              username: 'settings-test',
              is_active: true,
              is_staff: false,
              is_superuser: false
            }
          }
        else if (path === '/api/users/preferences/') body = { theme, has_particles: false }
        else if (path === '/api/projects/')
          body = [
            {
              slug: 'aesa',
              name: 'AESA',
              capabilities: ['compliance'],
              roles: { compliance: 'viewer', dcc: null, organization: null }
            }
          ]
        else if (path.endsWith('/compliance-documents/fields/'))
          body = {
            schema_version: 1,
            project: 'aesa',
            fields: [
              {
                key: 'name',
                label: 'Name',
                required: true,
                read_only: false,
                sortable: true,
                filter_kind: 'text'
              },
              {
                key: 'status',
                label: 'Status',
                required: false,
                read_only: false,
                sortable: false,
                filter_kind: 'none'
              },
              {
                key: 'tech_doc_no',
                label: 'Document number',
                required: false,
                read_only: false,
                sortable: true,
                filter_kind: 'text'
              }
            ]
          }
        else if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
        return route.fulfill({ json: body })
      })
      await page.goto('/app/compdocs/aesa')
      await page.getByRole('button', { name: 'Compliance document settings' }).click()
      await expect(page).toHaveURL(/compdocs\/settings\?project=aesa/)
      await expect(
        page.getByRole('heading', { name: 'Compliance document settings' })
      ).toBeVisible()
      const editor = page.locator('.column-editor')
      await expect(editor).toBeVisible()
      await expect(editor.locator('.column-row').first()).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(24, 24, 28)' : 'rgb(255, 255, 255)'
      )
      await page.locator('[aria-label="Rows per page"] input').fill('25')
      await page.locator('[aria-label="Rows per page"] input').blur()
      await page.getByRole('button', { name: 'Remove Status', exact: true }).click()
      await page.getByRole('button', { name: 'Move Document number up', exact: true }).click()
      page.once('dialog', (dialog) => dialog.dismiss())
      await page.getByRole('button', { name: 'Back to compliance documents' }).click()
      await expect(page).toHaveURL(/compdocs\/settings/)
      await page.getByRole('button', { name: 'Save settings', exact: true }).click()
      await expect(page.getByRole('button', { name: 'Save settings', exact: true })).toBeDisabled()
      await page.reload()
      await expect(page.locator('[aria-label="Rows per page"] input')).toHaveValue('25')
      await expect(editor.locator('.column-row')).toHaveCount(2)
      await expect(editor.locator('.column-row').first()).toHaveAttribute(
        'aria-label',
        'Document number'
      )
      await page.getByRole('button', { name: 'Recommended columns' }).click()
      await expect(editor.locator('.column-row')).toHaveCount(3)
      await page.getByRole('button', { name: 'Discard changes', exact: true }).click()
      await expect(editor.locator('.column-row')).toHaveCount(2)
      const dimensions = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth
      }))
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
      await page.screenshot({
        path: `test-results/compdoc-settings-${theme}-${width}.png`,
        fullPage: true
      })
      await page.goto('/app/compdocs/settings?project=forbidden')
      await expect(
        page.getByText("You do not have permission to view this project's compliance documents.")
      ).toBeVisible()
      await expect(editor).toHaveCount(0)
      await page.route(
        '**/api/projects/aesa/compliance-documents/fields/',
        (route) =>
          route.fulfill({
            status: 503,
            json: { detail: 'Schema temporarily unavailable.', code: 'unavailable' }
          }),
        { times: 1 }
      )
      await page.goto('/app/compdocs/settings?project=aesa')
      await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible()
      await expect(editor).toHaveCount(0)
      await page.getByRole('button', { name: 'Retry', exact: true }).click()
      await expect(editor.locator('.column-row')).toHaveCount(2)
    })
  }
}
