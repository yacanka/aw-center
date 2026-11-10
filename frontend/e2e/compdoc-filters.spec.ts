import { expect, test } from '@playwright/test'

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`panel and ATA filters stay independent and visible in ${theme} at ${width}px`, async ({
      page
    }) => {
      await page.setViewportSize({ width, height: 900 })
      const browserErrors: string[] = []
      page.on('pageerror', (error) => browserErrors.push(error.message))
      const queries: URLSearchParams[] = []
      const panels = [
        { id: 1, name: 'Systems', ata: '27-00', label: 'Systems · ATA 27-00' },
        { id: 2, name: 'Systems', ata: '28-00', label: 'Systems · ATA 28-00' },
        { id: 3, name: 'Structures', ata: '53-00', label: 'Structures · ATA 53-00' }
      ]
      await page.route('**/api/**', async (route) => {
        const url = new URL(route.request().url())
        const path = url.pathname
        if (!path.startsWith('/api/')) return route.fallback()
        let body: unknown = { count: 0, results: [], next: null, previous: null }
        if (path === '/api/session/')
          body = {
            state: 'authenticated',
            user: {
              id: 1,
              username: 'filter-test',
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
        else if (path.endsWith('/compliance-documents/fields/'))
          body = {
            schema_version: 4,
            project: 'ozgur',
            fields: ['name', 'panel', 'ata'].map((key) => ({
              key,
              label: key,
              required: false,
              read_only: false,
              width: 160,
              default_visible: true,
              sortable: true,
              ellipsis: false,
              filter_kind: key === 'name' ? 'text' : 'select',
              choices: [],
              option_source: key === 'panel' ? 'panels' : key === 'ata' ? 'atas' : null
            }))
          }
        else if (path.endsWith('/compliance-documents/options/'))
          body = { count: panels.length, results: panels, next: null, previous: null }
        else if (path.endsWith('/compliance-documents/statuses/')) body = []
        else if (path.endsWith('/compliance-documents/numbering-options/'))
          body = { provider: 'numarator', available: false, supports: [], formats: [] }
        else if (path.endsWith('/compliance-documents/')) queries.push(url.searchParams)
        else if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
        return route.fulfill({ json: body })
      })
      await page.goto('/app/compdocs/ozgur')
      await expect(page.locator('.protected-shell')).toBeVisible()
      expect(browserErrors).toEqual([])
      const panelIcon = page.getByLabel('Filter panel', { exact: true })
      const ataIcon = page.getByLabel('Filter ata', { exact: true })
      await expect(panelIcon).toBeVisible()
      const inactiveColor = await panelIcon.evaluate((node) => getComputedStyle(node).color)
      await panelIcon.click()
      await page.getByText('Systems', { exact: true }).click()
      await page
        .getByRole('button', { name: 'Confirm', exact: true })
        .filter({ visible: true })
        .click()
      await expect(page.getByText('Systems', { exact: true })).not.toBeVisible()
      await expect(panelIcon).toHaveClass(/compdoc-filter-icon--active/)
      await expect(panelIcon).toHaveCSS(
        'color',
        theme === 'dark' ? 'rgb(99, 226, 183)' : 'rgb(24, 160, 88)'
      )
      expect(await panelIcon.evaluate((node) => getComputedStyle(node).color)).not.toBe(
        inactiveColor
      )
      await expect(ataIcon).not.toHaveClass(/compdoc-filter-icon--active/)
      await expect.poll(() => queries.at(-1)?.getAll('panel_name')).toEqual(['Systems'])
      await ataIcon.click()
      await page.getByText('27-00', { exact: true }).click()
      await page
        .getByRole('button', { name: 'Confirm', exact: true })
        .filter({ visible: true })
        .click()
      await expect(page.getByText('27-00', { exact: true })).not.toBeVisible()
      await expect(ataIcon).toHaveClass(/compdoc-filter-icon--active/)
      await expect.poll(() => queries.at(-1)?.getAll('ata')).toEqual(['27-00'])
      expect(queries.at(-1)?.getAll('panel_name')).toEqual(['Systems'])
      await panelIcon.click()
      await page
        .getByRole('button', { name: 'Clear', exact: true })
        .filter({ visible: true })
        .click()
      await expect(panelIcon).not.toHaveClass(/compdoc-filter-icon--active/)
      await expect(ataIcon).toHaveClass(/compdoc-filter-icon--active/)
      await expect.poll(() => queries.at(-1)?.getAll('panel_name')).toEqual([])
      expect(queries.at(-1)?.getAll('ata')).toEqual(['27-00'])
      const dimensions = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth
      }))
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
      expect(browserErrors).toEqual([])
      await page.screenshot({
        path: `test-results/compdoc-filters-${theme}-${width}.png`,
        animations: 'disabled'
      })
      await page.getByRole('button', { name: 'New', exact: true }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      const references = dialog.locator('.n-card').filter({
        has: page.getByText('References', { exact: true })
      })
      await expect(references.locator('.n-form-item-label')).toHaveText([
        'Number',
        'Issue',
        'Cat',
        'MoC',
        'MoM No',
        'Requirements',
        'Reference Path'
      ])
      const number = references.locator('input').nth(0)
      const issue = references.locator('input').nth(1)
      await expect(number).toBeEditable()
      await number.fill('TD-123')
      await issue.fill('B')
      for (const label of ['Target Date', 'Revised Target Date', 'Release Date']) {
        await dialog.getByText(label, { exact: true }).scrollIntoViewIfNeeded()
        await expect(dialog.getByText(label, { exact: true })).toBeVisible()
      }
      await expect(dialog.getByText('Delivered', { exact: true })).toHaveCount(0)
      const dialogDimensions = await dialog.evaluate((node) => ({
        width: node.clientWidth,
        scroll: node.scrollWidth
      }))
      expect(dialogDimensions.scroll).toBeLessThanOrEqual(dialogDimensions.width + 1)
      expect(browserErrors).toEqual([])
      await page.screenshot({
        path: `test-results/compdoc-fields-${theme}-${width}.png`,
        animations: 'disabled',
        fullPage: true
      })
    })
  }
}
