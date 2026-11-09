import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'

async function sessionApi(page: Page, theme: 'light' | 'dark' = 'light', userId = 7) {
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/session/')
      return route.fulfill({
        json: {
          state: 'authenticated',
          user: {
            id: userId,
            username: 'mermaid-operator',
            is_active: true,
            is_staff: false,
            is_superuser: false,
            permissions: [],
            group_details: []
          }
        }
      })
    if (path === '/api/users/preferences/')
      return route.fulfill({ json: { theme, has_particles: false } })
    if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
    if (path === '/api/projects/') return route.fulfill({ json: [] })
    if (path === '/api/integrations/') return route.fulfill({ json: { integrations: [] } })
    return route.fulfill({ json: { count: 0, results: [], next: null, previous: null } })
  })
}
const code = (page: Page) => page.getByRole('textbox', { name: 'Mermaid kodu', exact: true })
const rendered = (page: Page) => page.getByRole('status').filter({ hasText: /^Çizim hazır$/ })

test('all ten templates render in the opaque sandbox without runtime network dependencies', async ({
  page
}) => {
  await sessionApi(page)
  const external: string[] = []
  page.on('request', (request) => {
    if (!request.url().startsWith('http://127.0.0.1:4173') && !/^(data:|blob:)/.test(request.url()))
      external.push(request.url())
  })
  await page.goto('/app/mermaid')
  await expect(rendered(page)).toBeVisible()
  await expect(page.locator('iframe')).toHaveAttribute('sandbox', 'allow-scripts')
  for (const label of [
    'Akış şeması',
    'Sıralama diyagramı',
    'Sınıf diyagramı',
    'Varlık ilişki diyagramı',
    'Durum diyagramı',
    'Gantt çizelgesi',
    'Pasta grafiği',
    'Zihin haritası',
    'Git dallanma grafiği',
    'Zaman çizelgesi'
  ]) {
    await page.getByRole('button', { name: 'Şablon ekle', exact: true }).click()
    await page
      .locator('.workshop-dialog')
      .getByRole('button', { name: new RegExp('^' + label) })
      .click()
    await expect(page.getByRole('textbox', { name: 'Şema başlığı' })).toHaveValue(label)
    await expect(rendered(page)).toBeVisible()
    await expect(page.frameLocator('iframe').locator('#diagram > svg')).toBeVisible()
  }
  expect(external).toEqual([])
  await expect(page.locator('.mermaid-workshop > svg')).toHaveCount(0)
})

test('recovers from errors, prevents stale export, and retains independent tab histories', async ({
  page
}) => {
  await sessionApi(page)
  await page.goto('/app/mermaid')
  await expect(rendered(page)).toBeVisible()
  await code(page).fill('flowchart LR\n A --> B')
  await expect(rendered(page)).toBeVisible()
  await code(page).fill('flowchart LR\n A --> [')
  await expect(page.getByRole('button', { name: 'Görsel aktar' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Hatalı satıra git' })).toBeVisible()
  await expect(page.frameLocator('iframe').locator('#diagram > svg')).toBeVisible()
  await page.getByRole('button', { name: 'Geri al', exact: true }).click()
  await expect(code(page)).toHaveValue('flowchart LR\n A --> B')
  await expect(rendered(page)).toBeVisible()
  await page.getByRole('button', { name: 'Şema ekle' }).click()
  await code(page).fill('flowchart LR\n X --> Y')
  await page.getByRole('tab', { name: 'Akış şeması', exact: true }).click()
  await expect(code(page)).toHaveValue('flowchart LR\n A --> B')
  await page.getByRole('button', { name: 'Yinele', exact: true }).click()
  await expect(code(page)).toHaveValue('flowchart LR\n A --> [')
  await code(page).fill('flowchart LR\n New --> Final')
  await code(page).fill('flowchart LR\n Current --> Result')
  await expect(rendered(page)).toBeVisible()
  await expect(page.frameLocator('iframe').locator('#diagram')).toContainText('Current')
  await expect(page.frameLocator('iframe').locator('#diagram')).not.toContainText('New')
})

test('round trips project files and downloads real SVG and PNG files', async ({ page }) => {
  await sessionApi(page)
  await page.goto('/app/mermaid')
  await expect(rendered(page)).toBeVisible()
  const fixture = {
    format: 'mermaid-atolyesi-project',
    version: 1,
    name: 'Dosya projesi',
    activeDiagramId: 'two',
    diagrams: [
      { id: 'one', title: 'Bir', code: 'flowchart LR\n A --> B', theme: 'studio' },
      { id: 'two', title: 'İki', code: 'sequenceDiagram\n Alice->>Bob: Merhaba', theme: 'dark' }
    ]
  }
  await page.locator('input[type=file]').setInputFiles({
    name: 'example.mmdproj',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(fixture))
  })
  await expect(page.getByRole('textbox', { name: 'Proje adı' })).toHaveValue('Dosya projesi')
  await expect(rendered(page)).toBeVisible()
  const saved = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Projeyi kaydet', exact: true }).click()
  expect(JSON.parse(await readFile((await (await saved).path())!, 'utf8'))).toEqual(fixture)
  for (const format of ['svg', 'png'] as const) {
    await page.getByRole('button', { name: 'Görsel aktar' }).click()
    if (format === 'png') {
      await page.getByRole('combobox', { name: 'Dosya biçimi' }).click()
      await page.getByText('PNG · Görsel', { exact: true }).last().click()
    }
    const downloaded = page.waitForEvent('download')
    await page.getByRole('button', { name: format.toUpperCase() + ' indir', exact: true }).click()
    const download = await downloaded,
      data = await readFile((await download.path())!)
    expect(download.suggestedFilename()).toBe(`İki.${format}`)
    if (format === 'svg') {
      expect(data.toString()).toContain('<svg')
      expect(data.toString()).not.toMatch(/<script|foreignObject|https:\/\/external/)
    } else {
      expect(data.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a')
      expect(data.readUInt32BE(16)).toBeGreaterThan(0)
    }
  }
})

test('restores account-scoped drafts and handles blocked storage without losing edits', async ({
  page
}) => {
  await sessionApi(page)
  await page.goto('/app/mermaid')
  await expect(rendered(page)).toBeVisible()
  await code(page).fill('flowchart LR\n Saved --> Local')
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('aw-center:mermaid:v1:7')))
    .toContain('Saved')
  await page.reload()
  await expect(code(page)).toHaveValue('flowchart LR\n Saved --> Local')
  await page.evaluate(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException('Full', 'QuotaExceededError')
    }
  })
  await code(page).fill('flowchart LR\n Keep --> Editing')
  await expect(page.getByText(/Otomatik saklama yapılamadı/)).toBeVisible()
  await expect(code(page)).toHaveValue('flowchart LR\n Keep --> Editing')
  await expect(page.getByRole('button', { name: 'Projeyi kaydet', exact: true })).toBeEnabled()
})

test('confirms destructive project actions and keeps a usable blank last tab', async ({ page }) => {
  await sessionApi(page)
  await page.goto('/app/mermaid')
  await expect(rendered(page)).toBeVisible()
  await code(page).fill('flowchart LR\n Keep --> This')
  await page.getByRole('button', { name: 'Yeni proje', exact: true }).click()
  await page.getByRole('button', { name: 'İptal', exact: true }).click()
  await expect(code(page)).toHaveValue('flowchart LR\n Keep --> This')
  await page.getByRole('button', { name: 'Akış şeması şemasını kaldır', exact: true }).click()
  await page.getByRole('button', { name: 'Kaldır', exact: true }).click()
  await expect(code(page)).toHaveValue('')
  await expect(page.getByRole('tab')).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Görsel aktar' })).toBeDisabled()
})

test('cancels pending project confirmations when navigating away', async ({ page }) => {
  await sessionApi(page)
  await page.goto('/app/home')
  await page.getByRole('menuitem', { name: 'Mermaid Atölyesi', exact: true }).click()
  await expect(rendered(page)).toBeVisible()
  await code(page).fill('flowchart LR\n Keep --> Draft')
  await page.getByRole('button', { name: 'Yeni proje', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Projeyi değiştir', exact: true })).toBeVisible()
  await page.goBack()
  await expect(page).toHaveURL(/\/app\/home$/)
  await expect(
    page.getByRole('button', { name: 'Projeyi değiştir', exact: true })
  ).not.toBeVisible()
  await page.getByRole('menuitem', { name: 'Mermaid Atölyesi', exact: true }).click()
  await expect(code(page)).toHaveValue('flowchart LR\n Keep --> Draft')
})

test('updates titles when importing a project with the same selected diagram id', async ({
  page
}) => {
  await sessionApi(page)
  await page.goto('/app/mermaid')
  await expect(rendered(page)).toBeVisible()
  const fixture = (title: string) => ({
    format: 'mermaid-atolyesi-project',
    version: 1,
    name: 'Same identity',
    activeDiagramId: 'same',
    diagrams: [{ id: 'same', title, code: 'flowchart LR\n A --> B', theme: 'studio' }]
  })
  for (const title of ['Original title', 'Updated title']) {
    await page.locator('input[type=file]').setInputFiles({
      name: 'updated.mmdproj',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(fixture(title)))
    })
    await expect(page.getByRole('textbox', { name: 'Şema başlığı' })).toHaveValue(title)
    await expect(page.getByRole('tab', { name: title, exact: true })).toHaveAttribute(
      'aria-selected',
      'true'
    )
  }
})

test('supports manual drawing, viewport controls and fullscreen', async ({ page }) => {
  await sessionApi(page)
  await page.goto('/app/mermaid')
  await expect(rendered(page)).toBeVisible()
  await page.getByRole('switch', { name: 'Canlı önizleme' }).click()
  await code(page).fill('flowchart LR\n Manual --> Drawing')
  await expect(page.getByRole('button', { name: 'Görsel aktar' })).toBeDisabled()
  await code(page).press('Control+Enter')
  await expect(rendered(page)).toBeVisible()
  await page.getByRole('button', { name: 'Gerçek boyuta dön' }).click()
  await expect(page.getByRole('button', { name: 'Gerçek boyuta dön' })).toHaveText('100%')
  await page.getByRole('button', { name: 'Yakınlaştır', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Gerçek boyuta dön' })).toHaveText('120%')
  await page.getByRole('button', { name: 'Tam ekran', exact: true }).click()
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(true)
  await page.getByRole('button', { name: 'Tam ekran', exact: true }).click()
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(false)
})

test('blocks active source and remote resources inside the renderer', async ({ page }) => {
  await sessionApi(page)
  const remote: string[] = [],
    dialogs: string[] = []
  await page.route('https://external.example/**', (route) => {
    remote.push(route.request().url())
    return route.abort()
  })
  page.on('dialog', async (dialog) => {
    dialogs.push(dialog.message())
    await dialog.dismiss()
  })
  await page.goto('/app/mermaid')
  await expect(rendered(page)).toBeVisible()
  await code(page).fill(
    '%%{init: {"securityLevel":"loose","htmlLabels":true,"themeCSS":"@import url(https://external.example/style.css)"}}%%\nflowchart LR\n A["<img src=x onerror=alert(1)>"] --> B'
  )
  await expect
    .poll(
      async () =>
        page.getByRole('button', { name: 'Görsel aktar' }).isEnabled() ||
        page.locator('.render-error').isVisible()
    )
    .toBe(true)
  await code(page).fill(
    'flowchart LR\n A@{ img: "https://external.example/image.png", label: "External" }'
  )
  await expect(page.locator('.render-error')).toBeVisible()
  expect(remote).toEqual([])
  expect(dialogs).toEqual([])
  const origin = await page
    .frameLocator('iframe')
    .locator('body')
    .evaluate(() => {
      try {
        return window.parent.document.title
      } catch {
        return 'isolated'
      }
    })
  expect(origin).toBe('isolated')
})

for (const theme of ['light', 'dark'] as const)
  for (const width of [390, 1440]) {
    test(`supports keyboard and responsive dialogs in ${theme} at ${width}px`, async ({
      page
    }, testInfo) => {
      await page.setViewportSize({ width, height: 900 })
      await sessionApi(page, theme)
      await page.goto('/app/mermaid')
      await expect(rendered(page)).toBeVisible()
      await code(page).focus()
      await code(page).press('Control+End')
      await code(page).press('Enter')
      await code(page).press('Tab')
      await expect(code(page)).toHaveValue(/\n {8}$/)
      await code(page).press('Escape')
      await code(page).press('Tab')
      await expect(code(page)).not.toBeFocused()
      if (width === 1440) {
        const separator = page.getByRole('separator', { name: 'Editör genişliği' })
        await separator.focus()
        await separator.press('ArrowRight')
        await expect(separator).toHaveAttribute('aria-valuenow', '42')
      }
      await page.screenshot({
        path: testInfo.outputPath(`mermaid-page-${theme}-${width}.png`),
        animations: 'disabled',
        fullPage: true
      })
      await page.getByRole('button', { name: 'Şablon ekle', exact: true }).click()
      await expect(page.getByRole('button', { name: /^Zihin haritası/ })).toBeVisible()
      await page.screenshot({
        path: testInfo.outputPath(`mermaid-${theme}-${width}.png`),
        animations: 'disabled',
        fullPage: true
      })
      const dimensions = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        width: document.documentElement.clientWidth
      }))
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1)
    })
  }
