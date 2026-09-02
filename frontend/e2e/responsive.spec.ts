import { expect, test, type Locator, type Page, type Route } from '@playwright/test'

const viewports = [
  { name: 'phone-320', width: 320, height: 568 },
  { name: 'phone-390', width: 390, height: 844 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'compact-1024', width: 1024, height: 768 },
  { name: 'desktop-1440', width: 1440, height: 900 },
  { name: 'wide-1920', width: 1920, height: 1080 }
]

const protectedRoutes = [
  '/app/home',
  '/app/integrations',
  '/app/jobs',
  '/app/accelerator',
  '/app/accelerator/outlook',
  '/app/task/ecr',
  '/app/settings',
  '/app/compare/excel',
  '/app/compare/word',
  '/app/compare/pdf',
  '/app/pdf/split',
  '/app/doors/scripter',
  '/app/doors/agent',
  '/app/developer/doors',
  '/app/teamcenter/agent',
  '/app/doors/poclinker',
  '/app/media-converter',
  '/app/translator',
  '/app/pptxGallery',
  '/app/users',
  '/app/organization',
  '/app/jira',
  '/app/ddfAssistant',
  '/app/compdocs/home',
  '/app/compdocs/aesa',
  '/app/compdocs/coverpagecreator',
  '/app/compdocs/docAnalyzer',
  '/app/unauthorized'
]

const anonymousSession = { state: 'anonymous', user: null }
const authenticatedSession = {
  state: 'authenticated',
  user: {
    id: 7,
    username: 'responsive-operator',
    email: 'responsive@example.test',
    first_name: 'Responsive',
    last_name: 'Operator',
    is_active: true,
    is_staff: true,
    is_superuser: true,
    permissions: [],
    group_details: []
  }
}

for (const viewport of viewports) {
  test(`layout remains usable at ${viewport.name}`, async ({ page }) => {
    test.setTimeout(120_000)
    await page.setViewportSize({ width: viewport.width, height: viewport.height })

    let authenticated = false
    const pageErrors: string[] = []
    page.on('pageerror', (error) => pageErrors.push(error.message))
    await routeResponsiveApi(page, () => authenticated)

    await page.goto('/app/login')
    await expect(page.getByRole('button', { name: 'Login' })).toBeVisible()
    await expectNoDocumentOverflow(page)
    await expectReadableFields(page)

    await page.getByText('Forgot Password?', { exact: true }).click()
    const resetDialog = page.locator('.n-modal.app-modal')
    await expect(resetDialog).toBeVisible()
    await expect(resetDialog.getByText('Reset Password', { exact: true })).toBeVisible()
    await expectNoElementOverflow(resetDialog.locator('.reset-status .n-tag__content'))
    await expectElementInsideViewport(resetDialog, viewport.width, viewport.height)
    await expectNoDocumentOverflow(page)

    authenticated = true
    for (const path of protectedRoutes) {
      await page.goto(path)
      await expect(page.locator('.protected-shell')).toBeVisible()
      await expectNoDocumentOverflow(page)

      const siderWidth = await page
        .locator('.protected-sider')
        .evaluate((element) => element.getBoundingClientRect().width)
      expect(Math.round(siderWidth), `${path} sider width`).toBe(viewport.width <= 900 ? 64 : 240)
    }

    expect(pageErrors).toEqual([])
  })
}

async function routeResponsiveApi(page: Page, isAuthenticated: () => boolean): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.fallback()

    if (path === '/api/session/') {
      return json(route, isAuthenticated() ? authenticatedSession : anonymousSession)
    }
    if (path === '/api/users/preferences/') return json(route, { has_particles: false })
    if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
    if (path === '/api/projects/') {
      return json(route, [
        {
          slug: 'aesa',
          name: 'AESA',
          capabilities: ['compliance', 'organization', 'dcc'],
          roles: { compliance: 'manager', organization: 'manager', dcc: 'publisher' }
        }
      ])
    }
    if (path.endsWith('/compliance-documents/fields/')) {
      return json(route, {
        schema_version: 1,
        project: 'aesa',
        fields: [
          { key: 'name', label: 'Name', required: true, read_only: false, visible: true },
          { key: 'status', label: 'Status', required: false, read_only: false, visible: true }
        ]
      })
    }
    if (path.endsWith('/system/')) {
      return json(route, { available: false, active_workers: 0, counts: {} })
    }
    if (path === '/api/attention/') {
      return json(route, { items: [], summary: { total: 0, critical: 0, warning: 0 } })
    }
    if (path === '/api/integrations/') return json(route, { integrations: [] })
    if (path === '/api/integrations/jira/session/') {
      return json(route, { state: 'disconnected', expires_at: null })
    }
    if (path === '/api/workflows/recipes/') return json(route, [])
    if (path.includes('/integrations/') && path.endsWith('/status/')) {
      return json(route, {
        configured: true,
        available: true,
        active_runners: 1,
        transport: 'loopback_token',
        auth_mode: 'service_account',
        service_root: 'https://integration.example.test',
        tls_verification_enabled: true
      })
    }

    return json(route, { count: 0, next: null, previous: null, results: [] })
  })
}

async function expectNoDocumentOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth
  }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1)
}

async function expectNoElementOverflow(locator: Locator): Promise<void> {
  const dimensions = await locator.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth
  }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1)
}

async function expectReadableFields(page: Page): Promise<void> {
  const widths = await page.locator('input:not([type="file"])').evaluateAll((elements) =>
    elements
      .filter((element) => {
        const rect = element.getBoundingClientRect()
        const style = window.getComputedStyle(element)
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden'
      })
      .map((element) => element.getBoundingClientRect().width)
  )
  expect(widths.length).toBeGreaterThan(0)
  expect(Math.min(...widths)).toBeGreaterThanOrEqual(180)
}

async function expectElementInsideViewport(
  locator: Locator,
  viewportWidth: number,
  viewportHeight: number
): Promise<void> {
  const rect = await locator.evaluate((element) => {
    const bounds = element.getBoundingClientRect()
    return {
      left: bounds.left,
      top: bounds.top,
      right: bounds.right,
      bottom: bounds.bottom
    }
  })
  expect(rect.left).toBeGreaterThanOrEqual(0)
  expect(rect.top).toBeGreaterThanOrEqual(0)
  expect(rect.right).toBeLessThanOrEqual(viewportWidth)
  expect(rect.bottom).toBeLessThanOrEqual(viewportHeight)
}

async function json(route: Route, body: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body)
  })
}
