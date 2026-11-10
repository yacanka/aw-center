import { expect, test } from '@playwright/test'

const metrics = {
  document_count: 4,
  issued_count: 1,
  approved_count: 1,
  approval_percentage: 25,
  scheduled_count: 4,
  schedule_variance: -3,
  high_risk_count: 0,
  action_overdue_count: 0,
  action_due_soon_count: 0,
  unassigned_count: 0,
  pending_review_count: 0,
  pending_approval_count: 0,
  data_quality_issue_count: 0
}

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`management reports capture, PDF and revoked access in ${theme} at ${width}px`, async ({
      page
    }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.emulateMedia({ colorScheme: theme })
      let saved = false
      let rejectOverview = false
      let rejectPdf = false
      const report = {
        id: null as string | null,
        title: 'Executive summary',
        management_note: '',
        captured_at: '2026-10-27T09:30:00Z',
        week_start: '2026-10-26',
        schema_version: 1,
        project_slugs: ['ozgur'],
        totals: metrics,
        projects: [{ slug: 'ozgur', display_name: 'Özgür', ...metrics }],
        priorities: []
      }
      const comparison = { available: false, baseline: null, elapsed_days: null, deltas: null }
      await page.route('**/api/**', async (route) => {
        const request = route.request()
        const path = new URL(request.url()).pathname
        let body: unknown = { count: 0, results: [], next: null, previous: null }
        if (path === '/api/session/') {
          body = rejectPdf
            ? { state: 'anonymous', user: null }
            : {
                state: 'authenticated',
                user: { id: 1, username: 'report-viewer', is_active: true }
              }
        } else if (path === '/api/users/preferences/') {
          body = { theme, has_particles: false }
        } else if (path === '/api/projects/') {
          body = []
        } else if (path === '/api/management-reports/options/') {
          body = { projects: [{ slug: 'ozgur', display_name: 'Özgür' }] }
        } else if (path === '/api/management-reports/overview/') {
          if (rejectOverview) {
            return route.fulfill({
              status: 403,
              json: { detail: 'Project access was revoked.', code: 'PERMISSION_DENIED' }
            })
          }
          body = { report, comparison }
        } else if (path === '/api/management-reports/reports/' && request.method() === 'POST') {
          const input = request.postDataJSON()
          expect(input).toEqual({
            project_slugs: ['ozgur'],
            title: 'Weekly review',
            management_note: 'Decision context'
          })
          Object.assign(report, {
            id: 'saved-report',
            title: input.title,
            management_note: input.management_note
          })
          saved = true
          return route.fulfill({ status: 201, json: { report, comparison } })
        } else if (path === '/api/management-reports/reports/') {
          body = {
            count: saved ? 1 : 0,
            results: saved ? [report] : [],
            next: null,
            previous: null
          }
        } else if (path === '/api/management-reports/reports/saved-report/') {
          body = { report, comparison }
        } else if (path === '/api/management-reports/reports/saved-report/pdf/') {
          if (rejectPdf) {
            return route.fulfill({
              status: 403,
              json: { detail: 'Session expired.', code: 'NOT_AUTHENTICATED' }
            })
          }
          return route.fulfill({ contentType: 'application/pdf', body: '%PDF-1.4\n%%EOF' })
        } else if (path.startsWith('/api/releases/')) {
          return route.fulfill({ status: 204 })
        }
        return route.fulfill({ json: body })
      })
      await page.goto('/app/management-reports')
      await expect(
        page.getByRole('heading', { name: 'Management Reports', exact: true })
      ).toBeVisible()
      await expect(
        page.getByText('Captured 27.10.2026 12:30:00 · Week of 26.10.2026')
      ).toBeVisible()
      await page.getByPlaceholder('Weekly executive review').fill('Weekly review')
      await page
        .getByPlaceholder('Add context and any decision you need from management.')
        .fill('Decision context')
      await page.getByRole('button', { name: 'Save current report', exact: true }).click()
      await expect(page.getByText('Saved snapshot', { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Open report', exact: true })).toBeVisible()
      await page.getByRole('button', { name: 'Open report', exact: true }).click()
      await expect(page.getByText('Decision context', { exact: true })).toBeVisible()
      const download = page.waitForEvent('download')
      await page.getByRole('button', { name: 'Download saved PDF', exact: true }).click()
      expect((await download).suggestedFilename()).toBe('Management Report saved-report.pdf')
      await page.screenshot({
        path: `test-results/reports-${theme}-${width}.png`,
        fullPage: true,
        animations: 'disabled'
      })
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1
        )
      ).toBe(true)
      rejectOverview = true
      await page.getByRole('button', { name: 'Refresh live overview', exact: true }).click()
      await expect(page.getByRole('alert')).toContainText('Project access was revoked.')
      await expect(page.getByText('Decision context', { exact: true })).toHaveCount(0)
      await page.getByRole('button', { name: 'Open report', exact: true }).click()
      await expect(page.getByText('Decision context', { exact: true })).toBeVisible()
      rejectPdf = true
      await page.getByRole('button', { name: 'Download saved PDF', exact: true }).click()
      await expect(page).toHaveURL(/\/app\/login/)
      await expect(page.getByText('Decision context', { exact: true })).toHaveCount(0)
    })
  }
}
