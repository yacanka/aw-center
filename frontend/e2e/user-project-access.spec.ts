import { expect, test } from '@playwright/test'

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`project access is visible in ${theme} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.emulateMedia({ colorScheme: theme })
      await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname
        if (!path.startsWith('/api/')) return route.fallback()
        let body: unknown = { count: 0, results: [], next: null, previous: null }
        if (path === '/api/session/') {
          body = {
            state: 'authenticated',
            user: { id: 1, username: '123456', is_staff: true, is_superuser: true, is_active: true }
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
            results: [
              {
                id: 2,
                username: '654321',
                is_active: false,
                project_access: [
                  {
                    project_id: 1,
                    project_name: 'Test project',
                    project_slug: 'test-project',
                    project_enabled: false,
                    domain: 'compliance',
                    application: 'Compliance documents',
                    role: 'manager',
                    sources: [
                      { kind: 'direct', group_id: null, group_name: null, role: 'viewer' },
                      { kind: 'group', group_id: 1, group_name: 'Reviewers', role: 'manager' }
                    ]
                  }
                ]
              }
            ]
          }
        } else if (path.startsWith('/api/releases/')) {
          return route.fulfill({ status: 204 })
        }
        return route.fulfill({ json: body })
      })
      await page.goto('/app/users')
      const directory = page.locator(width === 390 ? '.mobile-directory' : '.desktop-directory')
      await expect(
        directory.getByText('Test project · Compliance documents · manager (project disabled)')
      ).toBeVisible()
      await directory.getByRole('button', { name: 'Manage', exact: true }).click()
      const modal = page.locator('.user-editor')
      await expect(modal.getByText('Direct assignment · viewer')).toBeVisible()
      await expect(modal.getByText('Via role: Reviewers · manager')).toBeVisible()
      await expect(modal.getByText('Project disabled', { exact: true })).toBeVisible()
      await expect(modal).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(44, 44, 50)' : 'rgb(255, 255, 255)'
      )
      await page.screenshot({
        path: `test-results/project-access-${theme}-${width}.png`,
        fullPage: true,
        animations: 'disabled'
      })
      await modal.getByRole('button', { name: 'Cancel', exact: true }).click()
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1
        )
      ).toBe(true)
    })
  }
}
