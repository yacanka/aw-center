import { expect, test, type Page } from '@playwright/test'

const template = {
  id: 'dbe574a8-b4d3-4c87-9332-21153abcd001',
  name: 'Issue brief',
  version: 3,
  archived: false,
  project_id: '41',
  project_name: 'Flight systems',
  issue_type_id: '12',
  issue_type_name: 'Change',
  placeholders: [
    { name: 'Title', count: 2 },
    { name: 'Notes', count: 1 },
    { name: 'Owner', count: 1 }
  ],
  mapping: { Title: 'summary', Owner: 'assignee' }
}
const fields = [
  { id: 'summary', name: 'Summary', value: 'Review the test results', supported: true },
  { id: 'assignee', name: 'Assignee', value: '', supported: true },
  { id: 'customfield_17', name: 'Asset', value: '', supported: false }
]
const jira = '**/api/integrations/jira/'
const templatesPath = jira + 'document-templates/'
const resolvePath = jira + 'document-generation/resolve/'

async function shell(page: Page, theme: string, publisher = false) {
  await page.emulateMedia({ colorScheme: theme === 'dark' ? 'dark' : 'light' })
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let body: unknown = { count: 0, results: [] }
    const preferences = { theme, has_particles: false }
    if (path === '/api/session/')
      body = {
        state: 'authenticated',
        user: {
          id: 7,
          username: 'document-user',
          is_active: true,
          group_details: publisher
            ? [
                {
                  name: 'Publishers',
                  permissions: [
                    {
                      codename: 'manage_jira_document_templates',
                      content_type: { app_label: 'integrations' }
                    }
                  ]
                }
              ]
            : [],
          preferences
        }
      }
    else if (path === '/api/users/preferences/') body = preferences
    else if (path === '/api/projects/') body = []
    else if (path === '/api/integrations/jira/session/')
      body = {
        state: 'connected',
        user: { username: 'document-user', display_name: '' },
        expires_at: null
      }
    else if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
    return route.fulfill({ json: body })
  })
  await page.route(templatesPath, (route) => route.fulfill({ json: { templates: [template] } }))
  await page.route(resolvePath, (route) => {
    const { issue } = route.request().postDataJSON()
    const matches =
      issue === 'ABC-1'
        ? []
        : issue === 'ABC-2'
          ? [template, { ...template, id: 'second', name: 'Memo' }]
          : [template]
    return route.fulfill({ json: { ...template, issue, fields, templates: matches } })
  })
}
async function lookup(page: Page, key: string) {
  await page.getByPlaceholder('Issue key or JIRA browse URL').fill(key)
  await page.getByRole('button', { name: 'Look up issue' }).click()
}

for (const theme of ['light', 'dark']) {
  for (const width of [390, 1440]) {
    test(`generate a document without project roles in ${theme} at ${width}px`, async ({
      page
    }) => {
      await page.setViewportSize({ width, height: 900 })
      await shell(page, theme)
      const job = {
        id: 'queued-job',
        title: 'Create document for ABC-3',
        status: 'succeeded',
        progress: 100,
        message: 'Document created.',
        attempt: 1,
        max_attempts: 1,
        output_name: 'ABC-3.docx',
        download_url: '/api/jobs/queued-job/download/',
        can_cancel: false
      }
      await page.route(jira + 'document-generation/jobs/', (route) => {
        expect(route.request().postDataJSON()).toEqual({
          issue: 'ABC-3',
          template_id: template.id,
          version: 3,
          manual_values: { Notes: 'Verified' }
        })
        expect(route.request().headers()['idempotency-key']).toBeTruthy()
        return route.fulfill({ json: job })
      })
      await page.route('**/api/jobs/queued-job/download/', (route) =>
        route.fulfill({ contentType: 'application/octet-stream', body: 'fixture' })
      )
      await page.goto('/app/jira/documents')
      await page.getByText('Template library', { exact: true }).click()
      await expect(page.getByText(template.name, { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: 'New template' })).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Download source' })).toHaveCount(0)
      await page.getByText('Generate document', { exact: true }).click()
      await lookup(page, 'ABC-1')
      await expect(
        page.getByText('No active template matches this project and issue type.')
      ).toBeVisible()
      await lookup(page, 'ABC-2')
      await page.getByRole('textbox', { name: 'Matching templates' }).click()
      await page.getByText('Memo', { exact: true }).click()
      await expect(page.getByText('Review the test results')).toBeVisible()
      await page.getByRole('textbox', { name: 'Manual value for Notes' }).fill('previous issue')
      await lookup(page, 'ABC-3')
      await expect(page.getByText('Blank in document')).toBeVisible()
      const notes = page.getByRole('textbox', { name: 'Manual value for Notes' })
      await expect(notes).toHaveValue('')
      await notes.fill('Verified')
      await page.getByRole('button', { name: 'Generate DOCX' }).click()
      await expect(page.getByRole('button', { name: 'Show in Job Center' })).toBeVisible()
      const downloaded = page.waitForEvent('download')
      await page.getByRole('button', { name: 'Download DOCX' }).click()
      expect((await downloaded).suggestedFilename()).toBe('ABC-3.docx')
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true
      )
    })
  }
}

test('unavailable and unsupported mapped fields stop generation', async ({ page }) => {
  await shell(page, 'light')
  await page.route(resolvePath, (route) =>
    route.fulfill({
      json: {
        ...template,
        issue: 'ABC-4',
        fields: fields.filter((f) => f.id !== 'summary'),
        templates: [{ ...template, mapping: { Title: 'summary', Owner: 'customfield_17' } }]
      }
    })
  )
  await page.goto('/app/jira/documents')
  await lookup(page, 'ABC-4')
  await expect(page.getByText('Mapped field unavailable on this issue.')).toBeVisible()
  await expect(page.getByText('Unsupported JIRA field value.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Generate DOCX' })).toBeDisabled()
})

test('publisher replaces the source, retains matching fields and sees upload errors', async ({
  page
}) => {
  await shell(page, 'dark', true)
  let upload = 0
  const retained = [
    { name: 'Title', count: 3 },
    { name: 'New note', count: 1 }
  ]
  await page.route(templatesPath + 'inspect/', (route) => {
    upload++
    if (upload === 1)
      return route.fulfill({
        status: 400,
        json: {
          code: 'INVALID_FILE',
          detail: 'Upload rejected.',
          errors: { file: ['Select a Word DOCX file.'] }
        }
      })
    return route.fulfill({ json: { placeholders: retained } })
  })
  await page.route(templatesPath + template.id + '/', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: template })
    const body = route.request().postDataBuffer()?.toString() || ''
    expect(body).toContain('name="version"\r\n\r\n3')
    expect(body).toContain('{"Title":"summary"}')
    expect(body).toContain('ABC-3')
    return route.fulfill({
      json: { ...template, version: 4, placeholders: retained, mapping: { Title: 'summary' } }
    })
  })
  await page.goto('/app/jira/documents')
  await page.getByText('Template library', { exact: true }).click()
  await page.getByRole('button', { name: 'Edit template' }).click()
  const uploadInput = page.locator('input[type=file]')
  await uploadInput.setInputFiles({
    name: 'invalid.docx',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('invalid')
  })
  await expect(page.getByText(/Select a Word DOCX file/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  await uploadInput.setInputFiles({
    name: 'new.docx',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('fixture')
  })
  await expect(
    page.getByText('Placeholders removed by the replacement: Notes, Owner')
  ).toBeVisible()
  await expect(page.getByText('Title · 3 occurrences')).toBeVisible()
  await lookup(page, 'ABC-3')
  await expect(page.getByText('Summary (summary)', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText(/Flight systems · Change · Version 4/)).toBeVisible()
})

test('publisher creates a searchable mapping and archives the template', async ({ page }) => {
  await shell(page, 'light', true)
  const published = { ...template, name: 'Review memo', version: 1 }
  await page.route(templatesPath, (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { templates: [] } })
    const body = route.request().postDataBuffer()?.toString() || ''
    expect(body).toContain('{"Title":"summary"}')
    expect(body).toContain('Review memo')
    expect(body).toContain('ABC-3')
    return route.fulfill({ status: 201, json: published })
  })
  await page.route(templatesPath + 'inspect/', (route) =>
    route.fulfill({
      json: {
        placeholders: [
          { name: 'Title', count: 2 },
          { name: 'Notes', count: 1 }
        ]
      }
    })
  )
  await page.route(templatesPath + template.id + '/', (route) => {
    expect(route.request().postDataJSON()).toEqual({ version: 1, archived: true })
    return route.fulfill({ json: { ...published, archived: true, version: 2 } })
  })
  await page.goto('/app/jira/documents')
  await page.getByText('Template library', { exact: true }).click()
  await page.getByRole('button', { name: 'New template' }).click()
  await page.getByRole('textbox', { name: 'Template name' }).fill('Review memo')
  await page.locator('input[type=file]').setInputFiles({
    name: 'memo.docx',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('fixture')
  })
  await lookup(page, 'ABC-3')
  const field = page.getByRole('textbox', { name: 'Field for Title' })
  await field.click()
  await field.fill('sum')
  await page.getByText('Summary (summary)', { exact: true }).click()
  await expect(page.getByText('Review the test results')).toBeVisible()
  await page.getByRole('button', { name: 'Publish template' }).click()
  await expect(page.getByText('Review memo', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Archive', exact: true }).click()
  await page.getByRole('button', { name: 'Confirm' }).click()
  await expect(page.getByText('Archived', { exact: true })).toBeVisible()
})
