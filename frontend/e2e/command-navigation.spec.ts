import { expect, test, type Page } from '@playwright/test'

for (const theme of ['light', 'dark'] as const) {
  for (const width of [320, 1440]) {
    test(`quick command reserves shell space in ${theme} at ${width}px`, async ({
      page
    }, testInfo) => {
      await page.setViewportSize({ width, height: 768 })
      await routeShellApi(page, theme)
      await page.goto('/app/home')

      const trigger = page.getByRole('button', { name: /Quick command/ })
      await expect(trigger).toBeVisible()
      const triggerBounds = await trigger.boundingBox()
      const contentBounds = await page.locator('.protected-content').boundingBox()
      expect(triggerBounds).not.toBeNull()
      expect(contentBounds).not.toBeNull()
      expect(triggerBounds!.y + triggerBounds!.height).toBeLessThanOrEqual(contentBounds!.y)
      expect(triggerBounds!.x).toBeGreaterThanOrEqual(64)
      expect(triggerBounds!.x + triggerBounds!.width).toBeLessThanOrEqual(width)
      expect(triggerBounds!.height).toBeGreaterThanOrEqual(44)

      await trigger.click()
      const search = page.getByRole('textbox', { name: 'Search application commands' })
      await expect(search).toBeFocused()
      await page.screenshot({
        path: testInfo.outputPath('command-dialog.png'),
        animations: 'disabled'
      })
      await search.fill('PDF Split')
      await search.press('Enter')
      await expect(page).toHaveURL(/\/app\/pdf\/split$/)
      await expect(search).not.toBeVisible()

      for (const shortcut of ['Control+k', 'Meta+k']) {
        await page.keyboard.press(shortcut)
        await expect(search).toBeFocused()
        await page.keyboard.press('Escape')
        await expect(search).not.toBeVisible()
      }

      const dimensions = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        width: document.documentElement.clientWidth
      }))
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
      await page.screenshot({ path: testInfo.outputPath('command-shell.png') })
    })
  }
}

test('Jira navigation renders a theme-inheriting decorative vector icon', async ({ page }) => {
  await routeShellApi(page, 'light')
  await page.goto('/app/home')
  const jira = page.locator('.n-menu-item-content').filter({ hasText: /^JIRA$/ })
  const svg = jira.locator('svg')
  await expect(svg).toBeVisible()
  await expect(svg).toHaveAttribute('aria-hidden', 'true')
  await expect(svg).toHaveAttribute('focusable', 'false')
  await expect(svg.locator('path')).toHaveAttribute('fill', 'currentColor')
  await jira.click()
  await expect(page).toHaveURL(/\/app\/jira$/)
})

async function routeShellApi(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.fallback()
    if (path === '/api/session/') {
      return route.fulfill({
        json: {
          state: 'authenticated',
          user: {
            id: 7,
            username: 'command-operator',
            email: 'command@example.test',
            first_name: 'Command',
            last_name: 'Operator',
            is_active: true,
            is_staff: true,
            is_superuser: true,
            permissions: [],
            group_details: []
          }
        }
      })
    }
    if (path === '/api/users/preferences/') {
      return route.fulfill({ json: { theme, has_particles: false } })
    }
    if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
    if (path === '/api/projects/') {
      return route.fulfill({
        json: [
          {
            slug: 'aesa',
            name: 'AESA',
            capabilities: ['compliance', 'organization', 'jira'],
            roles: { compliance: 'viewer', organization: 'viewer', jira: 'viewer' }
          }
        ]
      })
    }
    if (path === '/api/attention/') {
      return route.fulfill({
        json: { items: [], summary: { total: 0, critical: 0, warning: 0 } }
      })
    }
    if (path === '/api/integrations/') return route.fulfill({ json: { integrations: [] } })
    if (path === '/api/integrations/jira/session/') {
      return route.fulfill({ json: { state: 'disconnected', expires_at: null } })
    }
    return route.fulfill({ json: { count: 0, results: [], next: null, previous: null } })
  })
}
