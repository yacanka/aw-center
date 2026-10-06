import { expect, test, type Page, type Route } from '@playwright/test'

const browserErrors = new WeakMap<Page, string[]>()
test.beforeEach(async ({ page }) => {
  const errors: string[] = []
  browserErrors.set(page, errors)
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.text().includes('Failed to resolve component')) errors.push(message.text())
  })
})
test.afterEach(async ({ page }) => {
  expect(browserErrors.get(page) || []).toEqual([])
})

const application = {
  id: 'pdf-split',
  title: 'PDF Splitter',
  path: '/pdf/split',
  description: 'Split a PDF into separate files.'
}
const reply = {
  answer: 'Open PDF Splitter and select the PDF you want to split.',
  applications: [application],
  sources: [{ id: application.id, title: application.title, path: application.path }]
}

async function shell(page: Page, theme = 'light') {
  let authenticated = true
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.fallback()
    if (path === '/api/session/') {
      if (route.request().method() === 'DELETE') authenticated = false
      if (route.request().method() === 'POST') authenticated = true
      return route.fulfill({
        headers: { 'set-cookie': 'csrftoken=assistant-fixture-csrf; Path=/; SameSite=Lax' },
        json: {
          state: authenticated ? 'authenticated' : 'anonymous',
          user: authenticated
            ? { id: 7, username: 'u12345', preferences: { theme, has_particles: false } }
            : null
        }
      })
    }
    if (path === '/api/users/preferences/')
      return route.fulfill({ json: { theme, has_particles: false } })
    if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
    if (path === '/api/projects/') return route.fulfill({ json: [] })
    if (path === '/api/attention/')
      return route.fulfill({ json: { items: [], summary: { total: 0, critical: 0, warning: 0 } } })
    if (path === '/api/integrations/assistant/catalog/')
      return route.fulfill({ json: { status: 'configured', applications: [application] } })
    if (path === '/api/integrations/assistant/chat/') return route.fulfill({ json: reply })
    return route.fulfill({ json: { count: 0, results: [], next: null, previous: null } })
  })
}

function panel(page: Page) {
  return page.getByRole('dialog', { name: 'AW Center Assistant' })
}

async function open(page: Page) {
  await page.getByRole('button', { name: 'Open AW Center Assistant' }).click()
  await expect(panel(page)).toBeVisible()
}

async function ask(page: Page, message = 'Where can I split a PDF?') {
  await page.getByRole('textbox', { name: 'Message to assistant' }).fill(message)
  await page.getByRole('button', { name: 'Send', exact: true }).click()
}

async function noOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth
  }))
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
  for (const name of ['Close assistant', 'New chat', 'Send']) {
    const bounds = await page.getByRole('button', { name, exact: true }).boundingBox()
    expect(bounds).not.toBeNull()
    expect(bounds!.x).toBeGreaterThanOrEqual(0)
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(dimensions.width + 1)
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1)
  }
}

test('lazy shell keeps chat across close, reopen and navigation; logout clears it', async ({
  page
}) => {
  await shell(page)
  let catalogs = 0
  let submitted: unknown
  await page.route('**/api/integrations/assistant/catalog/', async (route) => {
    catalogs += 1
    await route.fulfill({ json: { status: 'configured', applications: [application] } })
  })
  await page.route('**/api/integrations/assistant/chat/', async (route) => {
    expect(route.request().headers()['x-csrftoken']).toBe('assistant-fixture-csrf')
    submitted = route.request().postDataJSON()
    await route.fulfill({ json: reply })
  })
  await page.goto('/app/settings')
  await expect(page.getByRole('button', { name: 'Open AW Center Assistant' })).toBeVisible()
  expect(catalogs).toBe(0)
  await expect(page.getByTestId('assistant-panel')).toHaveCount(0)
  await open(page)
  await ask(page)
  await expect(page.getByRole('article', { name: 'Assistant response' })).toContainText(
    reply.answer
  )
  expect(submitted).toEqual({
    message: 'Where can I split a PDF?',
    history: [],
    current_path: '/settings'
  })
  await page.getByRole('button', { name: 'Open guide: PDF Splitter' }).click()
  await expect(page).toHaveURL(/\/app\/pdf\/split$/)
  await expect(page.getByRole('article', { name: 'Your message' })).toHaveCount(1)
  await page.getByRole('button', { name: 'Open PDF Splitter', exact: true }).click()
  await page.getByRole('button', { name: 'Close assistant' }).click()
  await expect(panel(page)).toHaveCount(0)
  await open(page)
  await expect(page.getByRole('article', { name: 'Assistant response' })).toContainText(
    reply.answer
  )
  expect(catalogs).toBe(1)
  await page.getByRole('button', { name: 'Close assistant' }).click()
  await page.getByRole('button', { name: /Account and settings:/ }).click()
  await expect(page).toHaveURL(/\/app\/settings$/)
  await page.getByRole('button', { name: /log ?out|sign out/i }).click()
  await expect(page).toHaveURL(/\/app\/login/)
  await expect(page.getByRole('button', { name: 'Open AW Center Assistant' })).toHaveCount(0)
  await page.getByPlaceholder('Enter your registration number').fill('u12345')
  await page.getByPlaceholder('Enter your password').fill('fixture-password')
  await page.getByRole('button', { name: 'Login', exact: true }).click()
  await open(page)
  await expect(page.getByRole('article', { name: 'Your message' })).toHaveCount(0)
  await expect(page.getByRole('article', { name: 'Assistant response' })).toHaveCount(0)
  expect(catalogs).toBe(2)
})

test('unconfigured service shows authorized guides without a generated answer', async ({
  page
}) => {
  await shell(page)
  await page.route('**/api/integrations/assistant/catalog/', (route) =>
    route.fulfill({ json: { status: 'unconfigured', applications: [application] } })
  )
  await page.goto('/app/settings')
  await open(page)
  await expect(panel(page)).toContainText('AI service is not configured.')
  await expect(page.getByRole('textbox', { name: 'Message to assistant' })).toBeDisabled()
  await expect(page.getByRole('article', { name: 'Available applications' })).toBeVisible()
  await expect(page.getByRole('article', { name: 'Assistant response' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Open PDF Splitter', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/pdf\/split$/)
})

test('retry repeats the failed request without duplicating the user message', async ({ page }) => {
  await shell(page)
  const requests: unknown[] = []
  await page.route('**/api/integrations/assistant/chat/', async (route) => {
    requests.push(route.request().postDataJSON())
    await route.fulfill(
      requests.length === 1
        ? {
            status: 503,
            json: { detail: 'The AI service is unavailable.', code: 'AI_UNAVAILABLE' }
          }
        : { json: reply }
    )
  })
  await page.goto('/app/settings')
  await open(page)
  await ask(page)
  await expect(page.getByRole('alert')).toContainText('The AI service is unavailable.')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('article', { name: 'Assistant response' })).toContainText(
    reply.answer
  )
  await expect(page.getByRole('article', { name: 'Your message' })).toHaveCount(1)
  expect(requests).toHaveLength(2)
  expect(requests[1]).toEqual(requests[0])
})

test('new chat fences a late response and accepts a fresh conversation', async ({ page }) => {
  await shell(page)
  let heldRoute: Route | undefined
  await page.route('**/api/integrations/assistant/chat/', async (route) => {
    heldRoute = route
  })
  await page.goto('/app/settings')
  await open(page)
  await ask(page, 'Old conversation')
  await expect.poll(() => Boolean(heldRoute)).toBe(true)
  await expect(page.getByRole('log')).toHaveAttribute('aria-busy', 'true')
  await page.getByRole('button', { name: 'New chat' }).click()
  await heldRoute!.fulfill({ json: { ...reply, answer: 'Late response from old conversation' } })
  await page.unroute('**/api/integrations/assistant/chat/')
  await ask(page, 'Fresh conversation')
  await expect(page.getByRole('article', { name: 'Assistant response' })).toContainText(
    reply.answer
  )
  await expect(panel(page)).not.toContainText('Late response from old conversation')
  await expect(page.getByRole('article', { name: 'Your message' })).toHaveCount(1)
  await page.getByRole('button', { name: 'New chat' }).click()
  await expect(page.getByRole('article')).toHaveCount(0)
})

test('literal model text cannot execute markup or introduce invalid navigation', async ({
  page
}) => {
  await shell(page)
  const malicious =
    '<img src=x onerror="window.assistantInjected=true"><script>window.assistantInjected=true</script> [Open](https://example.invalid)'
  await page.route('**/api/integrations/assistant/chat/', (route) =>
    route.fulfill({
      json: {
        answer: malicious,
        applications: [
          application,
          ...[
            'https://example.invalid',
            '//example.invalid',
            '/missing-route',
            '/settings?token=fixture'
          ].map((path, index) => ({
            ...application,
            id: `invalid-${index}`,
            title: `Invalid ${index}`,
            path
          }))
        ],
        sources: [{ id: 'invalid-source', title: 'Invalid source', path: 'javascript:alert(1)' }]
      }
    })
  )
  await page.goto('/app/settings')
  await open(page)
  await ask(page)
  const answer = page.getByRole('article', { name: 'Assistant response' })
  await expect(answer).toContainText(malicious)
  await expect(answer.locator('img, script, a')).toHaveCount(0)
  await expect(answer.getByRole('button')).toHaveCount(1)
  expect(await page.evaluate(() => 'assistantInjected' in window)).toBe(false)
  await expect(page).toHaveURL(/\/app\/settings$/)
})

test('keyboard opens, submits, traps focus and Escape restores the shell trigger', async ({
  page
}) => {
  await shell(page)
  await page.goto('/app/settings')
  const trigger = page.getByRole('button', { name: 'Open AW Center Assistant' })
  await trigger.focus()
  await page.keyboard.press('Enter')
  const input = page.getByRole('textbox', { name: 'Message to assistant' })
  await expect(input).toBeFocused()
  await input.fill('Where can I split a PDF?')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('article', { name: 'Assistant response' })).toBeVisible()
  await page.getByRole('button', { name: 'Close assistant' }).focus()
  await page.keyboard.press('Shift+Tab')
  expect(
    await page.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]')))
  ).toBe(true)
  await page.keyboard.press('Escape')
  await expect(panel(page)).toHaveCount(0)
  await expect(trigger).toBeFocused()
})

test('Integration Hub configuration is separate from live availability', async ({ page }) => {
  await shell(page)
  const queries: string[] = []
  await page.route('**/api/integrations/?*', async (route) => {
    queries.push(new URL(route.request().url()).search)
    await route.fulfill({
      json: {
        integrations: [
          {
            id: 'ai-chat',
            name: 'AI Chat Service',
            category: 'external',
            status: 'ready',
            configured: true,
            description: 'Configuration only; no live health probe.',
            capabilities: ['Chat'],
            route: null,
            platform: 'cross-platform'
          }
        ]
      }
    })
  })
  await page.route('**/api/integrations/', async (route) => {
    queries.push('')
    await route.fulfill({
      json: {
        integrations: [
          {
            id: 'ai-chat',
            name: 'AI Chat Service',
            category: 'external',
            status: 'ready',
            configured: true,
            description: 'Configuration only; no live health probe.',
            capabilities: ['Chat'],
            route: null,
            platform: 'cross-platform'
          }
        ]
      }
    })
  })
  await page.goto('/app/integrations')
  const card = page.locator('.integration-card').filter({ hasText: 'AI Chat Service' })
  await expect(card.getByText('Configured', { exact: true })).toBeVisible()
  await expect(card.getByText('available', { exact: true })).toHaveCount(0)
  await expect(card.getByRole('button', { name: 'Open', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Run live checks' }).click()
  await expect.poll(() => queries.length).toBe(2)
  await expect(card.getByText('available', { exact: true })).toHaveCount(0)
  await expect(page.getByText(/\d+ \/ \d+ live/)).toHaveCount(0)
})

for (const theme of ['light', 'dark'] as const) {
  for (const width of [375, 1440]) {
    test(`assistant chat layout in ${theme} at ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 })
      await page.emulateMedia({ colorScheme: theme })
      await shell(page, theme)
      await page.goto('/app/settings')
      await open(page)
      await ask(page)
      await expect(page.getByRole('article', { name: 'Assistant response' })).toBeVisible()
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      await expect(page.locator('.assistant-message').last()).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(24, 24, 28)' : 'rgb(255, 255, 255)'
      )
      await noOverflow(page)
      await page.screenshot({
        path: testInfo.outputPath(`assistant-${theme}-${width}.png`),
        fullPage: true
      })
    })
  }
  test(`assistant landscape in ${theme} respects reduced motion and viewport`, async ({
    page
  }, testInfo) => {
    await page.setViewportSize({ width: 820, height: 390 })
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await shell(page, theme)
    await page.goto('/app/settings')
    await open(page)
    await ask(page)
    await expect(page.getByRole('article', { name: 'Assistant response' })).toBeVisible()
    await noOverflow(page)
    await page.screenshot({
      path: testInfo.outputPath(`assistant-${theme}-landscape.png`),
      fullPage: true
    })
  })
}
