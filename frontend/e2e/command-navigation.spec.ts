import { dashboardSummary } from '../src/features/compliance/models/compdocDashboard.fixtures'
import { expect, test, type Page } from '@playwright/test'

for (const theme of ['light', 'dark'] as const) {
  for (const width of [320, 1440]) {
    test(`quick command reserves shell space in ${theme} at ${width}px`, async ({
      page
    }, testInfo) => {
      await page.setViewportSize({ width, height: 768 })
      await routeShellApi(page, theme)
      await page.goto('/app/home')

      const trigger = page.getByRole('button', { name: /Quick command/ })
      await expect(trigger).toBeVisible()
      const triggerBounds = await trigger.boundingBox()
      const contentBounds = await page.locator('.protected-content').boundingBox()
      const assistantBounds = await page
        .getByRole('button', { name: 'Open AW Center Assistant' })
        .boundingBox()
      const footerBounds = await page.locator('.protected-footer').boundingBox()
      const accountBounds = await page
        .getByRole('button', { name: /^Account and settings:/ })
        .boundingBox()
      expect(triggerBounds).not.toBeNull()
      expect(contentBounds).not.toBeNull()
      expect(assistantBounds).not.toBeNull()
      expect(footerBounds).not.toBeNull()
      expect(accountBounds).not.toBeNull()
      expect(contentBounds!.y + contentBounds!.height).toBeLessThanOrEqual(triggerBounds!.y)
      expect(triggerBounds!.y + triggerBounds!.height).toBeLessThanOrEqual(
        footerBounds!.y + footerBounds!.height
      )
      expect(Math.abs(triggerBounds!.y - assistantBounds!.y)).toBeLessThanOrEqual(1)
      expect(triggerBounds!.x + triggerBounds!.width + 8).toBeLessThanOrEqual(assistantBounds!.x)
      expect(Math.abs(footerBounds!.y - accountBounds!.y)).toBeLessThanOrEqual(1)
      expect(Math.abs(footerBounds!.height - accountBounds!.height)).toBeLessThanOrEqual(1)
      expect(triggerBounds!.x).toBeGreaterThanOrEqual(64)
      expect(triggerBounds!.x + triggerBounds!.width).toBeLessThanOrEqual(width)
      expect(triggerBounds!.height).toBeGreaterThanOrEqual(width < 600 ? 44 : 32)
      expect(footerBounds!.height).toBeLessThanOrEqual(width < 600 ? 70 : 60)
      await expect(trigger).toHaveText('Quick command')

      await trigger.click()
      const search = page.getByRole('textbox', { name: 'Search application commands' })
      await expect(search).toBeFocused()
      await expect(page.locator('.command-shortcut')).toBeVisible()
      await page.screenshot({
        path: testInfo.outputPath('command-dialog.png'),
        animations: 'disabled'
      })
      await search.fill('PDF Split')
      await search.press('Enter')
      await expect(page).toHaveURL(/\/app\/pdf\/split$/)
      await expect(search).not.toBeVisible()

      for (const shortcut of ['Control+k', 'Meta+k']) {
        await page.keyboard.press(shortcut)
        await expect(search).toBeFocused()
        await page.keyboard.press('Escape')
        await expect(search).not.toBeVisible()
      }

      const dimensions = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        width: document.documentElement.clientWidth
      }))
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
      await page.screenshot({ path: testInfo.outputPath('command-shell.png') })
    })
  }
}

test('Jira navigation renders a theme-inheriting decorative vector icon', async ({ page }) => {
  await routeShellApi(page, 'light')
  await page.goto('/app/home')
  const jira = page.locator('.n-menu-item-content').filter({ hasText: /^JIRA$/ })
  const svg = jira.locator('svg')
  await expect(svg).toBeVisible()
  await expect(svg).toHaveAttribute('aria-hidden', 'true')
  await expect(svg).toHaveAttribute('focusable', 'false')
  await expect(svg.locator('path')).toHaveAttribute('fill', 'currentColor')
  await jira.click()
  await expect(page).toHaveURL(/\/app\/jira$/)
})

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 1440]) {
    test(`compliance families and standalone projects render in ${theme} at ${width}px`, async ({
      page
    }, testInfo) => {
      await page.setViewportSize({ width, height: 900 })
      await routeShellApi(page, theme, true)
      await page.goto('/app/home')
      await page
        .locator('.n-menu-item-content')
        .filter({ hasText: /^Certification Dashboard$/ })
        .click()
      for (const name of [
        'GÖKBEY',
        'KAAN',
        'HÜRKUŞ-2',
        'HÜRJET',
        'ASOJ-STC1',
        'ASOJ-STC2',
        'Özgür',
        'BKM'
      ]) {
        const card = page.getByRole('button', { name, exact: true })
        await expect(card).toBeVisible()
        if (name === 'BKM') continue

        const artwork = card.locator('img')
        await expect(artwork).toHaveAttribute('alt', '')
        await expect
          .poll(() =>
            artwork.evaluate((image: HTMLImageElement) => {
              if (!image.complete || !image.naturalWidth) return false
              const canvas = document.createElement('canvas')
              const context = canvas.getContext('2d')!
              context.drawImage(image, 0, 0, 1, 1, 0, 0, 1, 1)
              return context.getImageData(0, 0, 1, 1).data[3] === 0
            })
          )
          .toBe(true)
      }
      const hasHorizontalOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
      )
      expect(hasHorizontalOverflow).toBe(false)
      await page.mouse.move(0, 0)
      await page.screenshot({
        path: testInfo.outputPath('certification-projects.png'),
        animations: 'disabled'
      })
      await page.getByRole('button', { name: 'Özgür', exact: true }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toHaveCSS('opacity', '1')
      await page.screenshot({
        path: testInfo.outputPath('certification-project-picker.png'),
        animations: 'disabled'
      })
      await dialog.getByRole('link', { name: 'HYS', exact: true }).click()
      await expect(page).toHaveURL(/compdocs\/hys\/dashboard$/)
      await page.getByRole('link', { name: 'Proje dokümanları' }).click()
      await expect(page).toHaveURL(/compdocs\/hys$/)
      await page.getByRole('link', { name: 'Proje grafikleri' }).click()
      await expect(page).toHaveURL(/compdocs\/hys\/dashboard$/)
    })
  }
}

test('project selection retries a failed catalog and handles an empty catalog', async ({
  page
}) => {
  await routeShellApi(page, 'light')
  let available = false
  await page.route('**/api/projects/', (route) =>
    route.fulfill(
      available ? { json: [] } : { status: 503, json: { detail: 'Catalog unavailable' } }
    )
  )
  await page.goto('/app/compdocs/home')
  const retry = page.getByRole('button', { name: 'Tekrar dene' })
  await expect(retry).toBeVisible()
  available = true
  await retry.click()
  await expect(page.getByText('Erişebileceğiniz proje bulunmuyor.')).toBeVisible()
})

test('a restricted project URL requests no analytics', async ({ page }) => {
  await routeShellApi(page, 'light')
  const analytics: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/compliance-documents/dashboard/')) analytics.push(request.url())
  })
  await page.goto('/app/compdocs/mmu/dashboard')
  await expect(page.getByText('Bu projeye erişiminiz yok.')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Proje dokümanları' })).toHaveCount(0)
  expect(analytics).toEqual([])
})

async function routeShellApi(
  page: Page,
  theme: 'light' | 'dark',
  allComplianceProjects = false
): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.fallback()
    if (path === '/api/session/') {
      return route.fulfill({
        json: {
          state: 'authenticated',
          user: {
            id: 7,
            username: 'command-operator',
            email: 'command@example.test',
            first_name: 'Command',
            last_name: 'Operator',
            is_active: true,
            is_staff: true,
            is_superuser: true,
            permissions: [],
            group_details: []
          }
        }
      })
    }
    if (path === '/api/users/preferences/') {
      return route.fulfill({ json: { theme, has_particles: false } })
    }
    if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
    if (path === '/api/projects/') {
      return route.fulfill({
        json: allComplianceProjects
          ? complianceProjects()
          : [
              {
                slug: 'aesa',
                name: 'AESA',
                capabilities: ['compliance', 'organization', 'jira'],
                roles: { compliance: 'viewer', organization: 'viewer', jira: 'viewer' }
              }
            ]
      })
    }
    if (path.endsWith('/compliance-documents/dashboard/')) {
      return route.fulfill({ json: dashboardSummary('hys') })
    }
    if (path === '/api/attention/') {
      return route.fulfill({
        json: { items: [], summary: { total: 0, critical: 0, warning: 0 } }
      })
    }
    if (path === '/api/integrations/') return route.fulfill({ json: { integrations: [] } })
    if (path === '/api/integrations/jira/session/') {
      return route.fulfill({ json: { state: 'disconnected', expires_at: null } })
    }
    return route.fulfill({ json: { count: 0, results: [], next: null, previous: null } })
  })
}

function complianceProjects() {
  return [
    ['aesa', 'AESA'],
    ['blok30', 'Blok 30'],
    ['blok4050', 'Blok 40/50'],
    ['hys', 'HYS'],
    ['gokbey', 'Gökbey'],
    ['gokbey_jandarma', 'Gökbey Jandarma'],
    ['havasoj_stc1', 'Havasoj STC1'],
    ['havasoj_stc2', 'Havasoj STC2'],
    ['hyeu', 'HYEU'],
    ['hurkus_aviyonik', 'Hürkuş Aviyonik'],
    ['hjt', 'HJT'],
    ['hsp', 'HSP'],
    ['navy', 'Navy'],
    ['bkm', 'BKM'],
    ['mmu', 'MMU']
  ].map(([slug, name]) => ({
    slug,
    name,
    capabilities: ['compliance', 'organization'],
    roles: { compliance: 'viewer', organization: 'viewer', jira: null }
  }))
}
