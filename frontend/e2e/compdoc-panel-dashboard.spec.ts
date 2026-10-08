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
          const overview = dashboardAnalytics(7, 27)
          overview.timeline.revised_scheduled = [{ x: '10.07.2026', y: 0 }]
          body = {
            ...summary,
            ...overview,
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
      const distributions = page.locator('.dashboard-column .dashboard-card')
      await expect(distributions).toHaveCount(2)
      const catCard = distributions.nth(1)
      await expect(catCard).toContainText('Document CAT')
      await expect(distributions.first().locator('.publication-group')).toHaveCount(2)
      await expect(distributions.first().locator('.publication-group').first()).toContainText(
        'Issued'
      )
      await expect(distributions.first().locator('.publication-group').last()).toContainText(
        'Not issued'
      )
      await expect(catCard.locator('.moc-distribution')).toContainText('Unspecified7100%')
      await expect(catCard.locator('.status-row')).toContainText('A7100%')
      // Distribution cards use a transparent gradient over the inherited theme surface.
      const cardTheme = await card.evaluate((node) =>
        getComputedStyle(node).getPropertyValue('--n-color')
      )
      await expect(catCard).toHaveCSS('--n-color', cardTheme)
      const statusBox = await distributions.first().boundingBox()
      const catBox = await catCard.boundingBox()
      const graphBox = await page.locator('.dashboard-grid').boundingBox()
      const riskBox = await page.locator('.risk-card').boundingBox()
      expect(catBox!.y).toBeGreaterThanOrEqual(statusBox!.y + statusBox!.height)
      expect(riskBox!.y).toBeGreaterThanOrEqual(graphBox!.y + graphBox!.height)
      expect(riskBox!.width).toBeCloseTo(graphBox!.width, 0)
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
      const timeline = page.locator('.timeline-surface canvas')
      await timeline.scrollIntoViewIfNeeded()
      // Read the real vue-chartjs instance to target a known intermediate day.
      const hoverPoint = await timeline.evaluate((canvas) => {
        const component = (
          canvas as unknown as {
            __vueParentComponent: { exposed: { chart: { value: import('chart.js').Chart } } }
          }
        ).__vueParentComponent
        const chart = component.exposed.chart.value
        const x = chart.scales.x.getPixelForValue(new Date(2026, 6, 5).getTime())
        return { x, y: (chart.chartArea.top + chart.chartArea.bottom) / 2 }
      })
      await timeline.hover({ position: hoverPoint })
      await expect
        .poll(() =>
          timeline.evaluate((canvas) => {
            const chart = (
              canvas as unknown as {
                __vueParentComponent: { exposed: { chart: { value: import('chart.js').Chart } } }
              }
            ).__vueParentComponent.exposed.chart.value
            return chart.tooltip?.dataPoints?.map((item) => ({
              label: item.dataset.label,
              value: item.parsed.y
            }))
          })
        )
        .toEqual([
          { label: 'Scheduled', value: 0 },
          { label: 'Actual', value: 7 },
          { label: 'Revised scheduled', value: 7 }
        ])
      await expect
        .poll(() =>
          timeline.evaluate((canvas) => {
            const chart = (
              canvas as unknown as {
                __vueParentComponent: { exposed: { chart: { value: import('chart.js').Chart } } }
              }
            ).__vueParentComponent.exposed.chart.value
            return chart.tooltip?.opacity
          })
        )
        .toBe(1)
      await page.screenshot({ path: `test-results/burndown-${theme}-${width}.png` })
      await expect(rows.first()).toContainText('27, 28')
      await rows.first().dblclick()
      await expect(rows.first()).toHaveAttribute('aria-selected', 'true')
      await expect(page.locator('.summary-meta')).toContainText('Systems · 27, 28')
      await expect(page.locator('.metrics .n-statistic').first()).toContainText('3')
      await expect(catCard.locator('.status-row')).toContainText('A3100%')
      await expect(catCard.locator('.moc-distribution')).toContainText('Unspecified3100%')
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
      await catCard.scrollIntoViewIfNeeded()
      await page.screenshot({ path: `test-results/cat-${theme}-${width}.png` })
      await page.locator('.risk-card').scrollIntoViewIfNeeded()
      await page.screenshot({ path: `test-results/risk-${theme}-${width}.png` })
      await tabs.getByRole('tab', { name: 'ATA based' }).click()
      await expect(rows).toHaveCount(3)
      await expect(page.locator('.metrics .n-statistic').first()).toContainText('7')
      await rows.first().dblclick()
      await expect(page.locator('.summary-meta')).toContainText('Systems · 27')
    })
  }
}
