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
      await page.goto('/app/')
      await expect(page).toHaveURL(/\/app\/login$/, { timeout: 3000 })
      await expect(page.getByRole('heading', { name: 'AW Center', exact: true })).toBeVisible()
      await expect(page.locator('.particle-text-canvas')).toHaveCount(0)
      await expect(page.locator('.particle-line')).toHaveText(['AW', 'Center'])
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
      const particles = page.locator('.particle-text-canvas')
      await expect(particles).toBeVisible()
      const geometry = await page.evaluate(() => {
        const [aw, center] = document.querySelectorAll('.particle-line')
        const tagline = document.querySelector('.tagline-copy')!
        const canvas = document.querySelector('.particle-text-canvas')!
        return {
          aw: aw!.getBoundingClientRect().toJSON(),
          center: center!.getBoundingClientRect().toJSON(),
          tagline: tagline.getBoundingClientRect().toJSON(),
          canvas: canvas.getBoundingClientRect().toJSON(),
          fontSize: parseFloat(getComputedStyle(aw!).fontSize)
        }
      })
      expect(geometry.center.top).toBeGreaterThan(geometry.aw.top)
      expect(Math.abs(geometry.aw.left - geometry.tagline.left)).toBeLessThan(2)
      expect(geometry.fontSize).toBeGreaterThanOrEqual(width === 1440 ? 100 : 48)
      expect(geometry.canvas.width).toBe(width)
      expect(geometry.canvas.height).toBe(900)
      await page.getByRole('textbox', { name: 'Username', exact: true }).fill('U12345')
      await expect(page.getByRole('textbox', { name: 'Username', exact: true })).toHaveValue(
        'U12345'
      )
      await page.waitForTimeout(1500)
      await page.screenshot({
        path: `test-results/login-particles-${theme}-${width}.png`,
        fullPage: true
      })
      if (theme === 'light' && width === 1440) {
        await page.mouse.move(geometry.aw.left + 70, geometry.aw.top + 45)
        await page.waitForTimeout(750)
        await page.screenshot({
          path: 'test-results/login-particles-scattered-light-1440.png',
          fullPage: true
        })
      }
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
