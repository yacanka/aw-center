import { expect, test, type Page } from '@playwright/test'

async function shell(page: Page, theme = 'light') {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.fallback()
    if (path === '/api/integrations/jira/session/') return route.fallback()
    if (path.startsWith('/api/releases/')) return route.fulfill({ status: 204 })
    let body: unknown = { count: 0, results: [] }
    if (path === '/api/session/')
      body = {
        state: 'authenticated',
        user: {
          id: 7,
          username: 'operator',
          permissions: [],
          is_superuser: false,
          preferences: { theme, has_particles: false }
        }
      }
    else if (path === '/api/users/preferences/') body = { theme, has_particles: false }
    else if (path === '/api/projects/')
      body = [
        {
          slug: 'hys',
          name: 'HYS',
          capabilities: ['jira'],
          roles: { jira: 'operator', compliance: null, organization: null }
        }
      ]
    else if (path.endsWith('/watcher/preferences/'))
      body = { outstanding_only: false, detail_fields: {} }
    await route.fulfill({ json: body })
  })
}

for (const theme of ['light', 'dark']) {
  for (const width of [390, 1440]) {
    test(`PAT login uses equal-width tabs and shows the verified account (${theme}, ${width})`, async ({
      page
    }) => {
      await page.setViewportSize({ width, height: 900 })
      await shell(page, theme)
      const user = {
        username: 'operator',
        display_name: 'A Jira User With A Long Display Name For Responsive Layout'
      }
      let connected = false
      let postStarted = false
      let release!: () => void
      const pending = new Promise<void>((resolve) => (release = resolve))
      await page.route('**/api/integrations/jira/session/', async (route) => {
        if (route.request().method() === 'POST') {
          expect(route.request().postDataJSON()).toEqual({ personal_access_token: 'fixture-token' })
          postStarted = true
          await pending
          connected = true
        } else if (route.request().method() === 'DELETE') {
          connected = false
          return route.fulfill({ status: 204 })
        }
        await route.fulfill({
          json: {
            state: connected ? 'connected' : 'disconnected',
            user: connected ? user : null,
            expires_at: null
          }
        })
      })
      await page.goto('/app/jira')
      const sessionTab = page.getByRole('tab', { name: 'Session ID', exact: true })
      const patTab = page.getByRole('tab', { name: 'Personal Access Token', exact: true })
      await expect(sessionTab).toHaveAttribute('aria-selected', 'true')
      await sessionTab.focus()
      await sessionTab.press('ArrowRight')
      await expect(patTab).toBeFocused()
      await expect(patTab).toHaveAttribute('aria-selected', 'true')
      await patTab.press('ArrowLeft')
      await expect(sessionTab).toBeFocused()
      await page
        .getByLabel('Session ID', { exact: true })
        .and(page.locator('input'))
        .fill('discard-this-session')
      await patTab.click()
      const username = page.getByLabel('AW Center username')
      await expect(username).toHaveValue('operator')
      await expect(username).toHaveAttribute('readonly', '')
      const token = page
        .getByLabel('Personal Access Token', { exact: true })
        .and(page.locator('input'))
      await expect(token).toHaveAttribute('type', 'password')
      await token.fill('discard-this-token')
      await sessionTab.click()
      await expect(
        page.getByLabel('Session ID', { exact: true }).and(page.locator('input'))
      ).toHaveValue('')
      await patTab.click()
      await expect(token).toHaveValue('')
      const sessionBounds = await sessionTab.boundingBox()
      const patBounds = await patTab.boundingBox()
      expect(Math.abs(sessionBounds!.width - patBounds!.width)).toBeLessThan(2)
      await page.screenshot({
        path: `test-results/jira-login-${theme}-${width}.png`,
        fullPage: true,
        animations: 'disabled'
      })
      await token.fill('fixture-token')
      await token.press('Enter')
      await expect.poll(() => postStarted).toBe(true)
      await expect(sessionTab).toHaveAttribute('aria-disabled', 'true')
      await expect(page.getByRole('button', { name: 'Connect', exact: true })).toBeDisabled()
      release()
      const account = page.getByText(`JIRA: ${user.display_name} (${user.username})`, {
        exact: true
      })
      await expect(account).toBeVisible()
      const accountBounds = await account.boundingBox()
      const tagBounds = await page.locator('.jira-account-tag').boundingBox()
      expect(accountBounds!.x + accountBounds!.width).toBeLessThanOrEqual(
        tagBounds!.x + tagBounds!.width
      )
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true
      )
      await page.screenshot({
        path: `test-results/jira-connected-${theme}-${width}.png`,
        fullPage: true,
        animations: 'disabled'
      })
      await page.reload()
      await expect(account).toBeVisible()
      await page.getByRole('button', { name: 'Disconnect from JIRA' }).click()
      await expect(page.getByRole('button', { name: 'Connect', exact: true })).toBeVisible()
      await expect(patTab).toHaveAttribute('aria-selected', 'true')
      await expect(
        page.getByLabel('Personal Access Token', { exact: true }).and(page.locator('input'))
      ).toHaveValue('')
    })
  }
}

test('remembers the last connection tab across reloads and visits without retaining credentials', async ({
  page
}) => {
  await shell(page)
  await page.route('**/api/integrations/jira/session/', (route) =>
    route.fulfill({ json: { state: 'disconnected', user: null, expires_at: null } })
  )
  await page.goto('/app/jira')
  const sessionTab = page.getByRole('tab', { name: 'Session ID', exact: true })
  const patTab = page.getByRole('tab', { name: 'Personal Access Token', exact: true })
  await expect(sessionTab).toHaveAttribute('aria-selected', 'true')
  await patTab.click()
  const token = page.getByLabel('Personal Access Token', { exact: true }).and(page.locator('input'))
  await token.fill('unsaved-token')
  await page.reload()
  await expect(patTab).toHaveAttribute('aria-selected', 'true')
  await expect(token).toHaveValue('')
  await page.goto('/app/')
  await page.goto('/app/jira')
  await expect(patTab).toHaveAttribute('aria-selected', 'true')
  await patTab.press('Home')
  await expect(sessionTab).toHaveAttribute('aria-selected', 'true')
  const session = page.getByLabel('Session ID', { exact: true }).and(page.locator('input'))
  await session.fill('unsaved-session')
  await page.reload()
  await expect(sessionTab).toHaveAttribute('aria-selected', 'true')
  await expect(session).toHaveValue('')
  const storage = await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))
  expect(storage).not.toContain('unsaved-token')
  expect(storage).not.toContain('unsaved-session')
})

test('Session ID login displays its real account and failed PAT attempts clear the field', async ({
  page
}) => {
  await shell(page)
  let connection = {
    state: 'disconnected',
    user: null as { username: string; display_name: string } | null,
    expires_at: null
  }
  await page.route('**/api/integrations/jira/session/', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON()
      if (body.personal_access_token)
        return route.fulfill({
          status: 400,
          json: {
            detail: 'Use a personal access token belonging to your AW Center username.',
            code: 'JIRA_ACCOUNT_MISMATCH'
          }
        })
      expect(body).toEqual({ JSESSIONID: 'fixture-session' })
      connection = {
        state: 'connected',
        user: { username: 'another-user', display_name: '' },
        expires_at: null
      }
    }
    await route.fulfill({ json: connection })
  })
  await page.goto('/app/jira')
  await page.getByRole('tab', { name: 'Personal Access Token', exact: true }).click()
  await page
    .getByLabel('Personal Access Token', { exact: true })
    .and(page.locator('input'))
    .fill('wrong-account-token')
  await page.getByRole('button', { name: 'Connect', exact: true }).click()
  await expect(
    page.getByText('Use a personal access token belonging to your AW Center username.')
  ).toBeVisible()
  await expect(
    page.getByLabel('Personal Access Token', { exact: true }).and(page.locator('input'))
  ).toHaveValue('')
  await page.getByRole('tab', { name: 'Session ID', exact: true }).click()
  await page
    .getByLabel('Session ID', { exact: true })
    .and(page.locator('input'))
    .fill('fixture-session')
  await page.getByRole('button', { name: 'Connect', exact: true }).click()
  await expect(page.getByText('JIRA: another-user', { exact: true })).toBeVisible()
})
