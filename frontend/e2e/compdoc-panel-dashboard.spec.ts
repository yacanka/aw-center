import { expect, test } from '@playwright/test'
import {
  dashboardAnalytics,
  dashboardSummary
} from '../src/features/compliance/models/compdocDashboard.fixtures'

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`panel breakdown modes inherit ${theme} theme at ${width}px`, async ({ page }) => {
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
              username: 'panel-test',
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
              roles: { compliance: 'manager', dcc: null, organization: null }
            }
          ]
        else if (path.endsWith('/compliance-documents/dashboard/')) {
          const summary = dashboardSummary()
          const structures = {
            id: 'panel-3',
            panel: 'Structures',
            ata: '53',
            analytics: dashboardAnalytics(4, 7)
          }
          body = {
            ...summary,
            ...dashboardAnalytics(7, 27),
            panels: [...summary.panels, structures],
            panel_groups: [...summary.panel_groups, { ...structures, id: 'panel:Structures' }]
          }
        } else if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
        return route.fulfill({ json: body })
      })

      await page.goto('/app/compdocs/home')
      const card = page.locator('.panel-breakdown')
      const rows = card.locator('tbody tr')
      await expect(rows).toHaveCount(2)
      await expect(card).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(24, 24, 28)' : 'rgb(255, 255, 255)'
      )
      const tabs = card.getByRole('tablist', { name: 'Panel breakdown mode' })
      const tabsBox = await tabs.boundingBox()
      const tableBox = await card.locator('.n-data-table').boundingBox()
      expect(tabsBox!.y + tabsBox!.height).toBeLessThanOrEqual(tableBox!.y)
      const panelTab = tabs.getByRole('tab', { name: 'Panel based' })
      expect(await tabs.getByRole('tab').allTextContents()).toEqual(['Panel based', 'ATA based'])
      await expect(panelTab).toHaveAttribute('aria-selected', 'true')
      await expect(panelTab).toHaveClass(/n-tabs-tab--active/)
      await expect(panelTab).toHaveCSS(
        'color',
        theme === 'dark' ? 'rgb(99, 226, 183)' : 'rgb(24, 160, 88)'
      )
      await expect(rows).toHaveCount(2)
      await expect(rows.first()).toContainText('27, 28')
      await rows.first().dblclick()
      await expect(rows.first()).toHaveAttribute('aria-selected', 'true')
      await expect(page.locator('.summary-meta')).toContainText('Systems · 27, 28')
      await expect(page.locator('.metrics .n-statistic').first()).toContainText('3')
      await rows.first().dblclick()
      await expect(page.locator('.metrics .n-statistic').first()).toContainText('7')
      await rows.first().focus()
      await rows.first().press('Enter')
      await expect(page.locator('.metrics .n-statistic').first()).toContainText('3')
      await expect(rows.first().locator('td').last()).toHaveText('3')
      const dimensions = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth
      }))
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
      await page.screenshot({ path: `test-results/panel-${theme}-${width}.png`, fullPage: true })
      await tabs.getByRole('tab', { name: 'ATA based' }).click()
      await expect(rows).toHaveCount(3)
      await expect(page.locator('.metrics .n-statistic').first()).toContainText('7')
      await rows.first().dblclick()
      await expect(page.locator('.summary-meta')).toContainText('Systems · 27')
    })
  }
}
