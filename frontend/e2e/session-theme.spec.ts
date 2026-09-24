import { expect, test } from '@playwright/test'

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`session pages inherit ${theme} theme at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.emulateMedia({ colorScheme: theme })
      let authenticated = false
      await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname
        if (!path.startsWith('/api/')) return route.fallback()
        let body: unknown = { count: 0, results: [], next: null, previous: null }
        if (path === '/api/session/') {
          body = {
            state: authenticated ? 'authenticated' : 'anonymous',
            user: authenticated
              ? { id: 1, username: '123456', is_staff: true, is_superuser: true, is_active: true }
              : null
          }
        } else if (path === '/api/users/preferences/') {
          body = { theme, has_particles: false }
        } else if (path === '/api/projects/') {
          body = []
        } else if (path === '/api/users/') {
          body = {
            count: 1,
            next: null,
            previous: null,
            results: [{ id: 2, username: '654321', is_staff: true, is_active: true }]
          }
        } else if (path.startsWith('/api/releases/')) {
          return route.fulfill({ status: 204 })
        }
        return route.fulfill({ json: body })
      })

      const surface = theme === 'dark' ? 'rgb(24, 24, 28)' : 'rgb(255, 255, 255)'
      const accent = theme === 'dark' ? 'rgb(99, 226, 183)' : 'rgb(24, 160, 88)'
      await page.goto('/app/login')
      await expect(page.locator('.login-panel')).toHaveCSS('background-color', surface)
      await expect(page.locator('.heading-dot')).toHaveCSS('color', accent)
      await page.evaluate(() =>
        window.dispatchEvent(new Event('beforeinstallprompt', { cancelable: true }))
      )
      const installPrompt = page.locator('.pwa-install-prompt')
      await expect(installPrompt).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(72, 72, 78)' : surface
      )
      const dismiss = page.getByRole('button', { name: 'Dismiss install suggestion' })
      await expect(dismiss.locator('svg')).toBeVisible()
      await dismiss.click()
      await expect(installPrompt).toHaveCount(0)
      await page.getByRole('button', { name: 'Forgot Password?' }).click()
      await expect(page.locator('.n-modal.app-modal')).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(44, 44, 50)' : surface
      )

      authenticated = true
      await page.goto('/app/users')
      await expect(page.locator('.users-admin')).toHaveCSS('background-color', surface)
      await expect(page.locator('.heading-dot')).toHaveCSS('color', accent)
      await expect(page.locator('.role-badge:visible').first()).toHaveCSS('color', accent)
      const dimensions = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth
      }))
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
      await page.screenshot({ path: `test-results/users-${theme}-${width}.png`, fullPage: true })
    })
  }
}
