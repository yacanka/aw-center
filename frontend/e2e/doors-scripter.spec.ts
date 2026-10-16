import { expect, test } from '@playwright/test'

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`DOORS mapping and script dialog use ${theme} theme at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 950 })
      await page.emulateMedia({ colorScheme: theme })
      const errors: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      let submitted = ''
      await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname
        if (!path.startsWith('/api/')) return route.fallback()
        if (path === '/api/session/')
          return route.fulfill({
            json: {
              state: 'authenticated',
              user: {
                id: 7,
                username: 'doors-test',
                is_active: true,
                is_staff: true,
                is_superuser: true,
                preferences: { theme, has_particles: false }
              }
            }
          })
        if (path === '/api/users/preferences/')
          return route.fulfill({ json: { theme, has_particles: false } })
        if (path === '/api/projects/') return route.fulfill({ json: [] })
        if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
        if (path === '/api/tools/excel/get_excel_columns/')
          return route.fulfill({ json: ['Key', 'Date'] })
        if (path === '/api/integrations/doors/script/') {
          submitted = route.request().postData() || ''
          return route.fulfill({
            json: { script: '// Review generated DXL', row_count: 1, mapping_count: 2 }
          })
        }
        return route.fulfill({ json: { count: 0, results: [], next: null, previous: null } })
      })

      await page.goto('/app/doors/scripter')
      await page.locator('input[type=file]').setInputFiles({
        name: 'mapping.xlsx',
        mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        buffer: Buffer.from('workbook upload boundary is mocked')
      })
      await page
        .getByRole('textbox', { name: 'DOORS attribute for Key', exact: true })
        .fill('Object Number')
      await page
        .getByRole('textbox', { name: 'DOORS attribute for Date', exact: true })
        .fill('Due Date')
      await page.getByRole('switch', { name: 'Unique Attribute for Key', exact: true }).click()
      const match = page.locator('.n-select[aria-label="Match mode for Key"]')
      await match.click()
      await page
        .locator('.n-base-select-option:visible')
        .filter({ hasText: /^Contains$/ })
        .click()
      await expect(match).toContainText('Contains')
      await page.getByRole('textbox', { name: 'Excel column Key', exact: true }).click()
      await expect(page.locator('.n-base-select-option:visible')).toHaveCount(0)
      const sizes = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth
      }))
      expect(sizes.scroll).toBeLessThanOrEqual(sizes.width + 1)
      await expect(page.locator('.n-card').first()).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(24, 24, 28)' : 'rgb(255, 255, 255)'
      )
      await page.screenshot({
        path: test.info().outputPath('mapping.png'),
        fullPage: true,
        animations: 'disabled'
      })
      await page.getByRole('button', { name: 'Generate', exact: true }).click()
      await expect(page.getByText('// Review generated DXL', { exact: true })).toBeVisible()
      expect(submitted).toContain('"match_mode":"contains"')
      expect(submitted).toContain('"doors":"Object Number"')
      await expect(page.locator('.n-modal.app-modal')).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(44, 44, 50)' : 'rgb(255, 255, 255)'
      )
      await expect(page.locator('.n-modal.app-modal')).toBeInViewport()
      await expect(page.locator('.n-modal.app-modal')).toHaveCSS('opacity', '1')
      await page.screenshot({
        path: test.info().outputPath('script-dialog.png'),
        fullPage: true,
        animations: 'disabled'
      })
      expect(errors).toEqual([])
    })
  }
}
