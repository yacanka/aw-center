import { expect, test, type Page, type Route } from '@playwright/test'
import type { IJiraField, ISubtaskListItem } from '../src/features/integrations/jira/models/jira'

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

test('fields remain editable after a delayed saved-list response and field reload', async ({
  page
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  let releaseContent!: () => void
  const contentReady = new Promise<void>((resolve) => {
    releaseContent = resolve
  })
  await jiraShell(page, contentReady)
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Loading saved lists')
  await page.getByPlaceholder('Enter Url').fill('CHN-42')
  await page.getByRole('button', { name: 'Load Fields', exact: true }).click()
  await expect(page.getByText('Fields Loaded', { exact: true })).toBeVisible()
  releaseContent()
  await expect(page.getByText('Review checklist', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Load Fields', exact: true }).click()
  await page.locator('.subtask-tools > .n-select').click()
  await page
    .locator('.n-base-select-option:visible')
    .filter({ hasText: /^Due Date$/ })
    .click()
  await page.getByPlaceholder('Enter Url').click()
  await expect(page.getByPlaceholder('Due Date')).toHaveCount(3)
  expect(errors).toEqual([])
})

test('field loading belongs to the generator actions next to Generate', async ({ page }) => {
  await jiraShell(page)
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  const actions = page.locator('.subtask-generator-actions')
  const load = actions.getByRole('button', { name: 'Load Fields', exact: true })
  await expect(load).toBeVisible()
  await expect(load).toBeDisabled()
  await expect(actions.getByRole('button', { name: 'Generate', exact: true })).toBeVisible()
  await expect(
    page.locator('.subtask-tools').getByRole('button', { name: 'Load Fields' })
  ).toHaveCount(0)
  await page.getByPlaceholder('Enter Url').fill('CHN-42')
  await expect(load).toBeEnabled()
  await load.click()
  await expect(page.getByText('Fields Loaded', { exact: true })).toBeVisible()
})

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`generator actions and field selection fit ${theme} mode at ${width}px`, async ({
      page
    }) => {
      const errors: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.setViewportSize({ width, height: 900 })
      await page.emulateMedia({ colorScheme: theme })
      await jiraShell(page)
      await page.goto('/app/jira?jira_tab=subtask')
      await expect(page.getByText('JIRA Subtask Generator', { exact: true })).toBeVisible()
      await page.getByPlaceholder('Enter Url').fill('CHN-42')
      const actions = page.locator('.subtask-generator-actions')
      await actions.getByRole('button', { name: 'Load Fields', exact: true }).click()
      await expect(page.getByText('Fields Loaded', { exact: true })).toBeVisible()
      await page.locator('.subtask-tools > .n-select').click()
      await page
        .locator('.n-base-select-option:visible')
        .filter({ hasText: /^Priority$/ })
        .click()
      await page.getByPlaceholder('Enter Url').click()
      await expect(page.locator('.n-base-select-option:visible')).toHaveCount(0)
      await expect(page.locator('.subtask-bulk-fields > *')).toHaveCount(3)
      const rowSummary = await page.locator('.n-dynamic-input-item .n-input').first().boundingBox()
      expect(rowSummary!.width).toBeGreaterThanOrEqual(160)
      await page.getByText('Release checklist', { exact: true }).click()
      await expect(page.getByPlaceholder('Summary').nth(1)).toHaveValue('Release')
      await page.getByText('Review checklist', { exact: true }).click()
      await expect(page.getByPlaceholder('Summary').nth(1)).toHaveValue('Review one')
      const load = await actions
        .getByRole('button', { name: 'Load Fields', exact: true })
        .boundingBox()
      const generate = await actions
        .getByRole('button', { name: 'Generate', exact: true })
        .boundingBox()
      expect(load).not.toBeNull()
      expect(generate).not.toBeNull()
      expect(load!.y).toBe(generate!.y)
      expect(generate!.x).toBeGreaterThanOrEqual(load!.x + load!.width)
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width
      )
      expect(errors).toEqual([])
      await page.screenshot({
        path: test.info().outputPath(`list-generator-${theme}-${width}.png`),
        fullPage: true
      })
    })
  }
}

for (const listKind of ['saved', 'new'] as const) {
  test(`first dynamic field can be added to a ${listKind} list without render errors`, async ({
    page
  }) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    const state = await jiraShell(page)
    state.content.lists[0].fields = []
    state.content.lists[0].list = [{ summary: 'Review', fields: {} }]
    await page.goto('/app/jira')
    await page.getByText('Subtask Generator (List)', { exact: true }).click()
    await expect(page.getByPlaceholder('Summary')).toHaveCount(2)
    if (listKind === 'new') {
      await page.locator('.n-tabs-tab--addable').click()
      await page.getByRole('button', { name: 'Add subtask row', exact: true }).click()
      await page.getByPlaceholder('Summary').nth(1).fill('New review')
    }
    await page.getByPlaceholder('Enter Url').fill('CHN-42')
    await page.getByRole('button', { name: 'Load Fields', exact: true }).click()
    await expect(page.getByText('Fields Loaded', { exact: true })).toBeVisible()
    await page.locator('.subtask-tools > .n-select').click()
    await page
      .locator('.n-base-select-option:visible')
      .filter({ hasText: /^Description$/ })
      .click()
    await page.getByPlaceholder('Enter Url').click()
    await expect(page.getByPlaceholder('Description')).toHaveCount(2)
    await page.getByPlaceholder('Description').nth(1).fill('Dynamic details')
    await saveLists(page)
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
    const saved = state.content.lists[listKind === 'new' ? 2 : 0]
    expect(saved.fields?.map((field) => field.id)).toEqual(['description'])
    expect(saved.list[0].fields?.description).toBe('Dynamic details')
    expect(errors).toEqual([])
  })
}

test('dynamic columns can be selected, cleared and selected again across list tabs', async ({
  page
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const state = await jiraShell(page)
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  await page.getByPlaceholder('Enter Url').fill('CHN-42')
  await page.getByRole('button', { name: 'Load Fields', exact: true }).click()
  await expect(page.getByText('Fields Loaded', { exact: true })).toBeVisible()
  for (const title of ['Review checklist', 'Release checklist', 'Review checklist']) {
    await page.getByText(title, { exact: true }).click()
    const picker = page.locator('.subtask-tools > .n-select')
    const list = state.content.lists.find((list) => list.title === title)!
    const selected = new Set(list.fields?.map((field) => field.id))
    for (const name of [
      'Due Date',
      'Priority',
      'Description',
      'Description',
      'Priority',
      'Due Date',
      'Description'
    ]) {
      await picker.click()
      await page
        .locator('.n-base-select-option:visible')
        .filter({ hasText: new RegExp(`^${name}$`) })
        .click()
      await page.getByPlaceholder('Enter Url').click()
      const id = fields.find((field) => field.name === name)!.id
      if (selected.has(id)) selected.delete(id)
      else selected.add(id)
      await expect(page.locator('.subtask-bulk-fields > *')).toHaveCount(selected.size + 1)
      expect(errors).toEqual([])
    }
    let releaseSave!: () => void
    state.saveReady = new Promise<void>((resolve) => {
      releaseSave = resolve
    })
    const savedVersion = state.content.version
    const savedResponse = page.waitForResponse(
      (response) =>
        response.request().method() === 'PUT' &&
        new URL(response.url()).pathname === '/api/integrations/jira/subtasks/saved-lists/'
    )
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
    expect(state.content.version).toBe(savedVersion)
    releaseSave()
    expect((await savedResponse).status()).toBe(200)
    expect(
      state.content.lists
        .find((list) => list.title === title)!
        .fields?.map((field) => field.id)
        .sort()
    ).toEqual([...selected].sort())
  }
})

test('custom field values survive bulk editing, Save, reload and Generate', async ({ page }) => {
  const metadata: IJiraField[] = [
    { id: 'customfield_10001', name: 'Acceptance criteria', schema: { type: 'string' } },
    { id: 'customfield_10002', name: 'Estimate', schema: { type: 'number' } },
    { id: 'customfield_10003', name: 'Verified', schema: { type: 'boolean' } },
    {
      id: 'customfield_10004',
      name: 'Category',
      schema: { type: 'option' },
      allowedValues: [{ id: '12', value: 'Review', label: 'Review' }]
    }
  ]
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const state = await jiraShell(page, Promise.resolve(), metadata)
  state.content.lists[0].fields = []
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  await page.getByPlaceholder('Enter Url').fill('CHN-42')
  await page.getByRole('button', { name: 'Load Fields', exact: true }).click()
  await expect(page.getByText('Fields Loaded', { exact: true })).toBeVisible()
  for (const field of metadata) {
    await page.locator('.subtask-tools > .n-select').click()
    await page
      .locator('.n-base-select-option:visible')
      .filter({ hasText: new RegExp(`^${field.name}$`) })
      .click()
    await page.getByPlaceholder('Enter Url').click()
  }
  const bulk = page.locator('.subtask-bulk-fields')
  await bulk.getByPlaceholder('Acceptance criteria').fill('Approved criteria')
  await bulk.getByPlaceholder('Estimate').fill('0')
  await bulk.locator('.n-select').nth(0).click()
  await page
    .locator('.n-base-select-option:visible')
    .filter({ hasText: /^False$/ })
    .click()
  await bulk.locator('.n-select').nth(1).click()
  await page
    .locator('.n-base-select-option:visible')
    .filter({ hasText: /^Review$/ })
    .click()
  await page.getByRole('button', { name: 'Set Values', exact: true }).click()
  await saveLists(page)
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  const expected = {
    description: 'Details one',
    customfield_10001: 'Approved criteria',
    customfield_10002: 0,
    customfield_10003: false,
    customfield_10004: '12'
  }
  expect(state.content.lists[0].list[0].fields).toEqual(expected)
  await page.reload()
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  await expect(page.getByPlaceholder('Acceptance criteria').nth(1)).toHaveValue('Approved criteria')
  await expect(page.getByPlaceholder('Estimate').nth(1)).toHaveValue('0')
  await page.getByPlaceholder('Enter Url').fill('CHN-42')
  await page.getByRole('button', { name: 'Generate', exact: true }).click()
  await expect
    .poll(() => state.created)
    .toMatchObject({
      issue: 'CHN-42',
      items: [
        {
          summary: 'Review one',
          description: 'Details one',
          fields: {
            customfield_10001: 'Approved criteria',
            customfield_10002: 0,
            customfield_10003: false,
            customfield_10004: '12'
          }
        },
        {
          summary: 'Review two',
          description: 'Details two',
          fields: {
            customfield_10001: 'Approved criteria',
            customfield_10002: 0,
            customfield_10003: false,
            customfield_10004: '12'
          }
        }
      ]
    })
  expect(errors).toEqual([])
})

test('live metadata can replace a saved editor type before adding another column', async ({
  page
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const metadata: IJiraField[] = [
    {
      id: 'customfield_10001',
      name: 'Category',
      schema: { type: 'option-with-child', custom: 'jira:cascadingselect' },
      allowedValues: [
        {
          id: '12',
          value: 'Parent',
          label: 'Parent',
          children: [{ id: '13', value: 'Child', label: 'Child' }]
        }
      ]
    },
    { id: 'customfield_10002', name: 'Notes', schema: { type: 'string' } }
  ]
  const state = await jiraShell(page, Promise.resolve(), metadata)
  state.content.lists[0].fields = [
    { id: 'customfield_10001', name: 'Category', schema: { type: 'string' } }
  ]
  state.content.lists[0].list = [{ summary: 'Review', fields: { customfield_10001: '12' } }]
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  await expect(page.getByPlaceholder('Category')).toHaveCount(2)
  await page.getByPlaceholder('Enter Url').fill('CHN-42')
  await page.getByRole('button', { name: 'Load Fields', exact: true }).click()
  await expect(page.getByText('Fields Loaded', { exact: true })).toBeVisible()
  await expect(page.getByText('Child option', { exact: true })).toHaveCount(1)
  await page.locator('.subtask-tools > .n-select').click()
  await page
    .locator('.n-base-select-option:visible')
    .filter({ hasText: /^Notes$/ })
    .click()
  await page.getByPlaceholder('Enter Url').click()
  await expect(page.getByPlaceholder('Notes')).toHaveCount(2)
  await page.getByPlaceholder('Notes').nth(1).fill('Updated notes')
  await saveLists(page)
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  expect(state.content.lists[0].list[0].fields?.customfield_10002).toBe('Updated notes')
  expect(errors).toEqual([])
})

test('dynamic fields can change while a saved-content error is visible', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const state = await jiraShell(page)
  state.failSave = true
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  await page.getByPlaceholder('Summary').nth(1).fill('Unsaved review')
  await page.getByPlaceholder('Enter Url').fill('CHN-42')
  await saveLists(page)
  await expect(page.getByRole('alert')).toContainText('Saved lists could not be saved.')
  await page.getByRole('button', { name: 'Load Fields', exact: true }).click()
  await expect(page.getByText('Fields Loaded', { exact: true })).toBeVisible()
  await page.locator('.subtask-tools > .n-select').click()
  await page
    .locator('.n-base-select-option:visible')
    .filter({ hasText: /^Due Date$/ })
    .click()
  await page.getByPlaceholder('Enter Url').click()
  await expect(page.getByPlaceholder('Due Date')).toHaveCount(3)
  state.failSave = false
  await saveLists(page)
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(state.content.lists[0].fields?.map((field) => field.id)).toEqual([
    'description',
    'duedate'
  ])
  expect(errors).toEqual([])
})

test('duplicate saved field definitions do not prevent adding live fields', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const state = await jiraShell(page)
  state.content.lists[0].fields = [fields[0], fields[0]]
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
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
  expect(errors).toEqual([])
})

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

  await saveLists(page)
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  expect(state.content.lists[0].title).toBe('Renamed checklist')
  expect(state.content.lists[0].fields?.map((field) => field.id)).toEqual([
    'description',
    'priority'
  ])
  expect(state.content.lists[1].list[0].summary).toBe('Release')

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

test('failed content saves retain unsaved edits and can be retried', async ({ page }) => {
  const state = await jiraShell(page)
  state.failSave = true
  await page.goto('/app/jira')
  await page.getByText('Subtask Generator (List)', { exact: true }).click()
  await page.getByPlaceholder('Summary').nth(1).fill('Unsaved review')
  await page.getByPlaceholder('Enter Url').click()
  await saveLists(page)
  await expect(page.getByRole('alert')).toContainText('Saved lists could not be saved.')
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeEnabled()
  expect(state.content.lists[0].list[0].summary).toBe('Review one')
  state.failSave = false
  await saveLists(page)
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  expect(state.content.lists[0].list[0].summary).toBe('Unsaved review')
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
  await saveLists(page)
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  expect(state.content.lists).toHaveLength(3)
  expect(state.content.lists[2].list).toEqual([{ summary: 'Second review', fields: {} }])
  await page
    .locator('.n-tabs-tab')
    .filter({ hasText: /^New List$/ })
    .getByRole('button', { name: 'close' })
    .click()
  await expect(page.getByText('New List', { exact: true })).toHaveCount(0)
  await saveLists(page)
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  expect(state.content.lists.map((list) => list.title)).toEqual([
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
  await page.getByPlaceholder('Enter Jira task URL or key').fill('CHN-42')
  await page.getByRole('button', { name: 'Load Fields', exact: true }).click()
  await expect(page.getByText('CHN-42: 4 subtask fields loaded.', { exact: false })).toBeVisible()
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
        page.locator('.n-base-select-option:visible').filter({ hasText: /^Summary \*$/ })
      ).toHaveClass(/n-base-select-option--disabled/)
    }
    await page
      .locator('.n-base-select-option:visible')
      .filter({ hasText: new RegExp(`^${name}( \\*)?$`) })
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
    page.locator('.n-base-select-option:visible').filter({ hasText: /^Summary \*$/ })
  ).not.toHaveAttribute('aria-disabled', 'true')
  await expect(page.locator('.n-base-select-option:visible')).toHaveCount(4)
})

async function jiraShell(
  page: Page,
  contentReady: Promise<void> = Promise.resolve(),
  fieldMetadata: IJiraField[] = fields
) {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.text().includes('Failed to resolve component')) errors.push(message.text())
  })
  const state = {
    content: {
      version: 0,
      lists: [
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
    saveReady: null as Promise<void> | null,
    created: null as unknown,
    workbookBody: ''
  }
  await page.route('**/api/session/', (route) =>
    json(route, {
      state: 'authenticated',
      user: { id: 7, username: 'operator', permissions: [], is_superuser: false }
    })
  )
  await page.route('**/api/users/preferences/', (route) => json(route, { theme: 'system' }))
  await page.route('**/api/integrations/jira/subtasks/saved-lists/', async (route) => {
    if (route.request().method() === 'PUT') {
      if (state.saveReady) await state.saveReady
      if (state.failSave)
        return json(route, { detail: 'Saved lists could not be saved.', code: 'SAVE_FAILED' }, 503)
      const payload = route.request().postDataJSON()
      state.content = { lists: payload.lists, version: state.content.version + 1 }
    }
    await contentReady
    return json(route, state.content)
  })
  await page.route('**/api/releases/**', (route) => route.fulfill({ status: 204 }))
  await page.route('**/api/projects/', (route) =>
    json(route, [
      {
        slug: 'hys',
        name: 'HYS',
        capabilities: ['jira'],
        roles: { jira: 'operator', compliance: null, organization: null }
      }
    ])
  )
  await page.route('**/api/integrations/jira/session/', (route) =>
    json(route, { state: 'connected', expires_at: '2027-01-01T00:00:00Z' })
  )
  await page.route('**/api/integrations/jira/watcher/preferences/', (route) =>
    json(route, { outstanding_only: false, detail_fields: {}, component_fields: {} })
  )
  await page.route('**/api/integrations/jira/records/**', (route) =>
    json(route, { count: 0, next: null, previous: null, results: [] })
  )
  await page.route('**/api/integrations/jira/subtasks/fields/', (route) => {
    if (route.request().postDataJSON().include_summary) {
      expect(route.request().postDataJSON()).toEqual({ issue: 'CHN-42', include_summary: true })
      return json(route, {
        issue: 'CHN-42',
        fields: [
          { id: 'summary', name: 'Summary', required: true, schema: { type: 'string' } },
          fields[0],
          { id: 'assignee', name: 'Assignee', schema: { type: 'user' } },
          fields[1]
        ]
      })
    }
    expect(route.request().postDataJSON()).toEqual({ issue: 'CHN-42' })
    return json(route, { issue: 'CHN-42', fields: fieldMetadata })
  })
  await page.route('**/api/integrations/jira/subtasks/workbook/', (route) =>
    json(route, { columns: ['Title', 'Details', 'Owner', 'Due'] })
  )
  await page.route('**/api/integrations/jira/subtasks/jobs/', (route) => {
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

async function saveLists(page: Page) {
  // A disabled Save button also means an in-flight write, so await persistence
  // before inspecting the saved fixture rather than relying on rendering speed.
  const response = page.waitForResponse(
    (result) =>
      result.request().method() === 'PUT' &&
      new URL(result.url()).pathname === '/api/integrations/jira/subtasks/saved-lists/'
  )
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await response
}
