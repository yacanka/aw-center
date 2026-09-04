import { expect, test, type Page, type Route } from '@playwright/test'
import type { ISubtaskListItem } from '../src/features/dcc/models/jira'

const fields = [
  { id: 'description', name: 'Description', schema: { type: 'string' } },
  { id: 'duedate', name: 'Due Date', schema: { type: 'date' } },
  {
    id: 'priority',
    name: 'Priority',
    schema: { type: 'priority' },
    allowedValues: [
      { value: 'High', label: 'High' },
      { value: 'Low', label: 'Low' }
    ]
  }
]

test('original named lists retain rename, bulk values, dynamic columns, Save and Generate', async ({
  page
}) => {
  const state = await jiraShell(page)
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  await expect(page.getByText('JIRA Subtask Generator', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  await expect(page.getByPlaceholder('Summary')).toHaveCount(3)

  await page.getByText('Review checklist', { exact: true }).dblclick()
  const title = page.locator('.n-tabs-tab input')
  await title.fill('Renamed checklist')
  await title.press('Enter')
  await page.getByPlaceholder('Summary').first().fill('Batch review')
  await page.getByPlaceholder('Description').first().fill('Bulk details')
  await page.getByRole('button', { name: 'Set Values' }).click()
  await expect(page.getByPlaceholder('Summary').nth(1)).toHaveValue('Batch review')
  await expect(page.getByPlaceholder('Summary').nth(2)).toHaveValue('Batch review')
  await expect(page.getByPlaceholder('Description').nth(2)).toHaveValue('Bulk details')

  await page.getByPlaceholder('Enter Url').fill('CHN-42')
  await page.getByRole('button', { name: 'Load Fields', exact: true }).click()
  await expect(page.getByText('Fields Loaded', { exact: true })).toBeVisible()
  await page.locator('.subtask-tools > .n-select').click()
  await page
    .locator('.n-base-select-option:visible')
    .filter({ hasText: /^Priority$/ })
    .click()
  await page.getByPlaceholder('Enter Url').click()
  await expect(
    page.locator('.subtask-bulk-fields').getByText('Priority', { exact: true })
  ).toBeVisible()

  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  expect(state.preferences.jira_list[0].title).toBe('Renamed checklist')
  expect(state.preferences.jira_list[0].fields?.map((field) => field.id)).toEqual([
    'description',
    'priority'
  ])
  expect(state.preferences.jira_list[1].list[0].summary).toBe('Release')

  await page.reload()
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  await expect(page.getByText('Renamed checklist', { exact: true })).toBeVisible()
  await expect(page.getByPlaceholder('Description').nth(1)).toHaveValue('Bulk details')
  await page.screenshot({ path: test.info().outputPath('list-generator.png'), fullPage: true })
  await page.getByText('Release checklist', { exact: true }).click()
  await expect(page.getByPlaceholder('Summary').nth(1)).toHaveValue('Release')
  await page.getByText('Renamed checklist', { exact: true }).click()
  await page.getByPlaceholder('Enter Url').fill('CHN-42')
  await page.getByRole('button', { name: 'Generate', exact: true }).click()
  await expect
    .poll(() => state.created)
    .toEqual({
      issue: 'CHN-42',
      items: [
        {
          summary: 'Batch review',
          description: 'Bulk details',
          assignee: '',
          due_date: null,
          fields: {}
        },
        {
          summary: 'Batch review',
          description: 'Bulk details',
          assignee: '',
          due_date: null,
          fields: {}
        }
      ]
    })
  await expect(page.getByText('Subtasks created successfully.', { exact: true })).toBeVisible()
  await expect(page.locator('.subtask-progress .n-progress')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Create subtasks', exact: true })).toHaveCount(0)
})

test('failed preference saves retain unsaved edits and can be retried', async ({ page }) => {
  const state = await jiraShell(page)
  state.failSave = true
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  await page.getByPlaceholder('Summary').nth(1).fill('Unsaved review')
  await page.getByPlaceholder('Enter Url').click()
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByText('Preferences could not be saved.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeEnabled()
  expect(state.preferences.jira_list[0].list[0].summary).toBe('Review one')
  state.failSave = false
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  expect(state.preferences.jira_list[0].list[0].summary).toBe('Unsaved review')
})

test('saved list tabs and subtask rows can be added and removed without changing other lists', async ({
  page
}) => {
  const state = await jiraShell(page)
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  await page.locator('.n-tabs-tab--addable').click()
  await expect(page.getByText('New List', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Add subtask row', exact: true }).click()
  await page.getByPlaceholder('Summary').nth(1).fill('New review')
  await page.locator('.n-dynamic-input-item__action').first().getByRole('button').last().click()
  await expect(page.getByPlaceholder('Summary')).toHaveCount(3)
  await page.getByPlaceholder('Summary').nth(2).fill('Second review')
  await page.locator('.n-dynamic-input-item__action').first().getByRole('button').first().click()
  await expect(page.getByPlaceholder('Summary')).toHaveCount(2)
  await expect(page.getByPlaceholder('Summary').nth(1)).toHaveValue('Second review')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  expect(state.preferences.jira_list).toHaveLength(3)
  expect(state.preferences.jira_list[2].list).toEqual([{ summary: 'Second review', fields: {} }])
  await page
    .locator('.n-tabs-tab')
    .filter({ hasText: /^New List$/ })
    .getByRole('button', { name: 'close' })
    .click()
  await expect(page.getByText('New List', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  expect(state.preferences.jira_list.map((list) => list.title)).toEqual([
    'Review checklist',
    'Release checklist'
  ])
})

test('original Excel tab keeps the four field mappings and clears them on file removal', async ({
  page
}) => {
  const state = await jiraShell(page)
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (Excel)', { exact: true }).click()
  await expect(page.getByText('JIRA Subtask Generator from Excel', { exact: true })).toBeVisible()
  await page.getByPlaceholder('Enter Url').fill('CHN-42')
  const upload = {
    name: 'subtasks.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: Buffer.from('mocked-workbook')
  }
  await page.locator('input[type="file"]').setInputFiles(upload)
  await expect(page.getByText('Excel Column Names', { exact: true })).toBeVisible()
  await expect(page.getByText('JIRA Field Names', { exact: true })).toBeVisible()
  const mappings = page.locator('.n-select')
  await expect(mappings).toHaveCount(4)
  for (const [index, name] of ['Summary', 'Description', 'Assignee', 'Due Date'].entries()) {
    await mappings.nth(index).click()
    if (index === 1) {
      await expect(
        page.locator('.n-base-select-option:visible').filter({ hasText: /^Summary$/ })
      ).toHaveClass(/n-base-select-option--disabled/)
    }
    await page
      .locator('.n-base-select-option:visible')
      .filter({ hasText: new RegExp(`^${name}$`) })
      .click()
    await expect(page.locator('.n-base-select-option:visible')).toHaveCount(0)
  }
  await page.screenshot({ path: test.info().outputPath('excel-generator.png'), fullPage: true })
  await page.getByRole('button', { name: 'Generate', exact: true }).click()
  await expect.poll(() => state.workbookBody).toContain('"column":"Title","field":"summary"')
  expect(state.workbookBody).toContain('"column":"Details","field":"description"')
  expect(state.workbookBody).toContain('"column":"Owner","field":"assignee"')
  expect(state.workbookBody).toContain('"column":"Due","field":"duedate"')
  expect(state.workbookBody).not.toMatch(/JSESSIONID|credential/)
  await expect(page.getByText('Subtasks created successfully.', { exact: true })).toBeVisible()
  await page.locator('.n-upload-file-info__action button').click()
  await expect(mappings).toHaveCount(0)
  await page.locator('input[type="file"]').setInputFiles(upload)
  await expect(mappings).toHaveCount(4)
  await mappings.first().click()
  await expect(
    page.locator('.n-base-select-option:visible').filter({ hasText: /^Summary$/ })
  ).not.toHaveAttribute('aria-disabled', 'true')
  await expect(page.locator('.n-base-select-option:visible')).toHaveCount(4)
})

async function jiraShell(page: Page) {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.text().includes('Failed to resolve component')) errors.push(message.text())
  })
  const state = {
    preferences: {
      jira_list: [
        {
          title: 'Review checklist',
          fields: [fields[0]],
          list: [
            { summary: 'Review one', fields: { description: 'Details one' } },
            { summary: 'Review two', fields: { description: 'Details two' } }
          ]
        },
        { title: 'Release checklist', fields: [], list: [{ summary: 'Release' }] }
      ] as ISubtaskListItem[]
    },
    failSave: false,
    created: null as unknown,
    workbookBody: ''
  }
  await page.route('**/api/session/', (route) =>
    json(route, {
      state: 'authenticated',
      user: { id: 7, username: 'operator', permissions: [], is_superuser: false }
    })
  )
  await page.route('**/api/users/preferences/', async (route) => {
    if (route.request().method() === 'PATCH') {
      if (state.failSave)
        return json(route, { detail: 'Preferences could not be saved.', code: 'SAVE_FAILED' }, 503)
      state.preferences = route.request().postDataJSON()
    }
    return json(route, state.preferences)
  })
  await page.route('**/api/releases/**', (route) => route.fulfill({ status: 204 }))
  await page.route('**/api/projects/', (route) =>
    json(route, [
      {
        slug: 'hys',
        name: 'HYS',
        capabilities: ['dcc'],
        roles: { dcc: 'operator', compliance: null, organization: null }
      }
    ])
  )
  await page.route('**/api/integrations/jira/session/', (route) =>
    json(route, { state: 'connected', expires_at: '2027-01-01T00:00:00Z' })
  )
  await page.route('**/api/dcc/records/**', (route) =>
    json(route, { count: 0, next: null, previous: null, results: [] })
  )
  await page.route('**/api/dcc/subtasks/fields/', (route) => {
    expect(route.request().postDataJSON()).toEqual({ issue: 'CHN-42' })
    return json(route, { issue: 'CHN-42', fields })
  })
  await page.route('**/api/dcc/subtasks/workbook/', (route) =>
    json(route, { columns: ['Title', 'Details', 'Owner', 'Due'] })
  )
  await page.route('**/api/dcc/subtasks/jobs/', (route) => {
    expect(route.request().headers()['idempotency-key']).toBeTruthy()
    if (route.request().headers()['content-type']?.includes('multipart')) {
      state.workbookBody = route.request().postData() || ''
    } else {
      state.created = route.request().postDataJSON()
    }
    expect(errors).toEqual([])
    return json(route, subtaskJob('queued'))
  })
  await page.route('**/api/jobs/subtask-job/', (route) => json(route, subtaskJob('succeeded')))
  return state
}

function subtaskJob(status: string) {
  return {
    id: 'subtask-job',
    kind: 'dcc.create_jira_subtasks',
    status,
    progress: status === 'succeeded' ? 100 : 0,
    message:
      status === 'succeeded' ? 'Subtasks created successfully.' : 'Preparing subtask creation...',
    result_summary: {}
  }
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}
