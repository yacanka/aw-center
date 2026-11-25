import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { expect, test } from '@playwright/test'
import { dashboardSummary } from '../src/features/compliance/models/compdocDashboard.fixtures'
import type { ViewerDocument } from '../src/viewer/api'

for (const [width, theme] of [
  [1440, 'light'],
  [1440, 'dark'],
  [390, 'light'],
  [390, 'dark']
] as const) {
  test(`standalone dashboard, drill-down and refresh at ${width}px in ${theme}`, async ({
    page
  }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.emulateMedia({ colorScheme: theme })
    const session = randomUUID()
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    const queries: string[] = []
    let returnAesaRows!: () => void
    const aesaRowsReady = new Promise<void>((resolve) => {
      returnAesaRows = resolve
    })
    const source = {
      projects: [
        { slug: 'ozgur', name: 'OZGUR' },
        { slug: 'aesa', name: 'AESA' }
      ],
      source_kind: 'backup',
      read_at: '2026-11-25T09:00:00Z',
      warning: ''
    }
    const summary = dashboardSummary()
    summary.panels[0].id = '21'
    summary.panels[1].id = '22'
    const first: ViewerDocument = {
      id: summary.risk.priorities[0].document_id,
      name: 'Read-only document',
      number: 'DOC-01',
      status: 'to_be_issued',
      panel: 'Systems',
      panel_id: '21',
      ata: '27',
      cat: 'A',
      trimmed_cat: 'A',
      delivery_bucket: 'delayed',
      moc: '0',
      issue: '2',
      cover_page_no: 'C1',
      cover_page_issue: '1',
      target_date: '2026-11-25',
      revised_target_date: null,
      release_date: null,
      next_action_due_date: null
    }
    const rows = [
      first,
      {
        ...first,
        id: randomUUID(),
        name: 'Other ATA',
        panel_id: '22',
        ata: '28',
        delivery_bucket: 'expected',
        trimmed_cat: 'B',
        number: 'DOC-02'
      }
    ]
    let failRefresh = false
    const unexpected: string[] = []
    const dist = resolve('dist-viewer')

    await page.route('**/*', async (route) => {
      const req = route.request()
      const { origin, pathname, search } = new URL(req.url())
      if (origin === 'http://127.0.0.1:28754') {
        if (pathname === '/ui/test/') {
          const index = await readFile(resolve(dist, 'index.html'), 'utf-8')
          return route.fulfill({
            contentType: 'text/html',
            body: index.replace('__DASHBOARD_SESSION__', session)
          })
        }
        if (/^\/assets\/[\w.-]+\.(js|css)$/.test(pathname))
          return route.fulfill({ path: resolve(dist, pathname.slice(1)) })
        if (
          pathname.startsWith('/viewer/') &&
          !search &&
          req.headers()['x-dashboard-session'] === session
        ) {
          queries.push(`${req.method()} ${pathname}`)
          if (pathname === '/viewer/projects') return route.fulfill({ json: source })
          if (pathname === '/viewer/refresh' && req.method() === 'POST')
            return failRefresh
              ? route.fulfill({ status: 409, json: { detail: 'Ağ yedeğine erişilemiyor.' } })
              : route.fulfill({ json: { ...source, read_at: '2026-11-25T09:10:00Z' } })
          if (pathname.endsWith('/dashboard'))
            return route.fulfill({ json: { ...summary, project: pathname.split('/')[3] } })
          if (pathname === '/viewer/projects/aesa/documents') {
            await aesaRowsReady
            return route.fulfill({ json: [] })
          }
          if (pathname.endsWith('/documents')) return route.fulfill({ json: rows })
        }
      }
      unexpected.push(pathname)
      await route.abort()
    })

    await page.goto('/ui/test/')
    await expect(page.getByText('Son okuma', { exact: false })).toContainText('25.11.2026 12:00:00')
    await expect(page.getByText('Active documents', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await expect(page.getByText('Son okuma', { exact: false })).toContainText('12:10:00')
    expect(queries.slice(-2)).toEqual([
      'POST /viewer/refresh',
      'GET /viewer/projects/ozgur/dashboard'
    ])
    failRefresh = true
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await expect(page.getByText('Ağ yedeğine erişilemiyor.', { exact: false })).toBeVisible()
    await expect(page.getByText('Active documents', { exact: true })).toBeVisible()
    await expect(page.getByText('Son okuma', { exact: false })).toContainText('12:10:00')
    failRefresh = false
    await page.getByRole('tab', { name: 'ATA based' }).click()
    await page.getByRole('row', { name: 'Focus Systems · 27', exact: true }).press('Enter')
    await page.getByRole('link', { name: 'Delayed', exact: true }).click()
    await expect(page).toHaveURL(/dashboard_panel_id=21/)
    await expect(page.getByRole('button', { name: first.name })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Other ATA' })).toHaveCount(0)
    await page.getByRole('button', { name: first.name }).click()
    const detail = page.getByRole('dialog')
    await expect(detail).toContainText('25.11.2026')
    await expect(detail).toContainText('DOC-01')
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Yenile' }).click()
    await expect
      .poll(() => queries.slice(-2))
      .toEqual(['POST /viewer/refresh', 'GET /viewer/projects/ozgur/documents'])
    await page.getByRole('link', { name: 'Dashboard', exact: true }).click()
    await page.getByRole('link', { name: 'A', exact: true }).click()
    await expect(page.getByRole('button', { name: first.name })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Other ATA' })).toHaveCount(0)
    await page.getByRole('link', { name: 'Dashboard', exact: true }).click()
    await page.getByText('Synthetic overdue document', { exact: true }).click()
    await page.getByRole('button', { name: 'Review document' }).click()
    await expect(detail).toContainText(first.name)
    await expect(detail).toContainText('DOC-01')
    await page.keyboard.press('Escape')
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
    ).toBe(true)
    await page.locator('.project-controls .n-select').click()
    await page.getByText('AESA', { exact: true }).click()
    await expect.poll(() => queries.at(-1)).toBe('GET /viewer/projects/aesa/documents')
    await expect(page.getByRole('button', { name: first.name })).toHaveCount(0)
    returnAesaRows()
    await expect(page.getByText('0 doküman', { exact: true })).toBeVisible()
    source.projects = []
    await page.getByRole('button', { name: 'Yenile' }).click()
    await expect(page.getByText('Kaynakta görüntülenebilecek proje bulunamadı.')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toHaveCount(0)
    expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0])
    expect(page.url().includes(session)).toBe(false)
    expect(errors).toEqual([])
    expect(unexpected).toEqual([])
  })
}
