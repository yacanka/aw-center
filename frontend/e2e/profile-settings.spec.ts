import { expect, test } from '@playwright/test'

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`edits own profile in ${theme} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.emulateMedia({ colorScheme: theme })
      let profile = { first_name: 'Before', last_name: 'User', email: 'before@example.com' }
      let failSave = false
      let writes = 0
      await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname
        if (!path.startsWith('/api/')) return route.fallback()
        if (path === '/api/session/') {
          return route.fulfill({
            json: { state: 'authenticated', user: { id: 1, username: 'U12345', ...profile } }
          })
        }
        if (path === '/api/users/preferences/') {
          return route.fulfill({ json: { theme, has_particles: false } })
        }
        if (path === '/api/users/profile/' && route.request().method() === 'PATCH') {
          writes++
          if (failSave) {
            return route.fulfill({
              status: 400,
              json: { detail: 'Profile could not be saved.', code: 'VALIDATION_ERROR' }
            })
          }
          profile = route.request().postDataJSON()
          return route.fulfill({ json: profile })
        }
        if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
        return route.fulfill({ json: [] })
      })

      await page.goto('/app/settings')
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      await page.getByLabel('First name', { exact: true }).fill('Ada')
      await page.getByLabel('Last name', { exact: true }).fill('Lovelace')
      await page.getByLabel(/^Email address/).fill('ada@example.com')
      await page.getByRole('button', { name: 'Save profile' }).click()
      await expect(page.locator('#account-heading')).toHaveText('Ada Lovelace')
      await expect(page.locator('.account-details')).toContainText('ada@example.com')
      await expect(page.getByRole('button', { name: 'Save profile' })).toBeDisabled()
      expect(writes).toBe(1)
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width
      )
      await page.screenshot({ path: `test-results/profile-${theme}-${width}.png`, fullPage: true })
      await page.reload()
      await expect(page.getByLabel('First name', { exact: true })).toHaveValue('Ada')

      failSave = true
      await page.getByLabel('First name', { exact: true }).fill('Draft')
      await page.getByRole('button', { name: 'Save profile' }).click()
      await expect(page.getByRole('alert')).toContainText('Profile could not be saved.')
      await expect(page.locator('#account-heading')).toHaveText('Ada Lovelace')
      await expect(page.getByLabel('First name', { exact: true })).toHaveValue('Draft')
      await expect(page.getByRole('button', { name: 'Save profile' })).toBeEnabled()
    })
  }
}
