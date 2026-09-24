import { expect, test } from '@playwright/test'

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`login tagline in ${theme} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.route('**/api/**', (route) => {
        if (!new URL(route.request().url()).pathname.startsWith('/api/')) return route.fallback()
        return route.fulfill({ json: { state: 'anonymous', user: null } })
      })
      await page.goto('/app/login')
      const tagline = page.locator('.tagline-copy')
      await expect(tagline).toHaveText('Less routine. More room for your expertise.')
      await expect(page.getByRole('button', { name: 'Pause animation' })).toHaveCount(0)
      await expect(page.locator('.login-panel')).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(24, 24, 28)' : 'rgb(255, 255, 255)'
      )
      await page.screenshot({
        path: `test-results/login-tagline-${theme}-${width}.png`,
        fullPage: true
      })
      await page.emulateMedia({ reducedMotion: 'no-preference' })
      await expect(
        page.getByRole('button', { name: /Pause animation|Resume animation/ })
      ).toHaveCount(0)
      await expect(page.locator('.tagline-copy .cursor')).toBeVisible()
      const dimensions = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth
      }))
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width)
    })
  }
}
