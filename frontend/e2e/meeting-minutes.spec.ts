import { expect, test } from '@playwright/test'

for (const [theme, width] of [
  ['light', 1440],
  ['dark', 390]
] as const) {
  test(`meeting actions can be reviewed and published in ${theme} at ${width}px`, async ({
    page
  }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.emulateMedia({ colorScheme: theme })
    const job = {
      id: 'source',
      kind: 'jira.read_meeting_minutes',
      status: 'succeeded',
      input_name: 'minutes.docx',
      jira_draft: { id: 'draft', status: 'published' }
    }
    const draft = {
      id: 'draft',
      source_job: 'source',
      summary: 'Meeting review',
      description: 'Decisions',
      status: 'published',
      project_key: 'CHN',
      jira_issue_key: 'CHN-42',
      version: 4,
      events: [],
      project_slugs: ['hys'],
      allowed_actions: {},
      extra_fields: {}
    }
    const responses: Record<string, unknown> = {
      'session/': {
        state: 'authenticated',
        user: { id: 7, username: 'operator', permissions: [], is_superuser: false }
      },
      'users/preferences/': { theme: 'system' },
      'projects/': [
        {
          slug: 'hys',
          name: 'HYS',
          capabilities: ['jira'],
          roles: { jira: 'publisher', organization: null, compliance: null }
        }
      ],
      'integrations/jira/session/': { state: 'connected', expires_at: '2027-01-01T00:00:00Z' },
      'integrations/jira/meeting-minutes/jobs/': job,
      'integrations/jira/issue-drafts/draft/': draft
    }
    let published: unknown
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname.slice('/api/'.length)
      if (path.startsWith('releases/')) return route.fulfill({ status: 204 })
      if (path === 'integrations/jira/meeting-minutes/draft/actions/') {
        if (route.request().method() === 'POST') {
          published = route.request().postDataJSON()
          return route.fulfill({ json: { id: 'batch' } })
        }
        return route.fulfill({
          json: {
            actions: [
              {
                no: '1',
                action_item: 'Review checklist',
                responsible: 'Team',
                due_date: '20.11.2026'
              },
              { no: '2', action_item: 'Excluded', responsible: '', due_date: '' }
            ],
            fields: []
          }
        })
      }
      return route.fulfill({ json: responses[path] ?? {} })
    })
    await page.goto('/app/jira?jira_tab=minutes')
    await expect(page.getByRole('button', { name: 'Read meeting minutes (.docx)' })).toBeVisible()
    await page.locator('input[type=file]').setInputFiles({
      name: 'minutes.docx',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('upload-fixture')
    })
    await page.getByRole('button', { name: 'Review meeting actions' }).click()
    await page.getByText('Include action 2').click()
    const submit = page.getByRole('button', { name: 'Create selected subtasks' })
    await submit.click()
    await page.getByRole('button', { name: 'Confirm', exact: true }).click()
    await expect(page.getByRole('link', { name: 'Open subtask job' })).toHaveAttribute(
      'href',
      /job=batch/
    )
    expect(published).toMatchObject({
      items: [{ summary: 'Review checklist', due_date: '2026-11-20' }]
    })
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width
    )
  })
}
