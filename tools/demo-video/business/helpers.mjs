import path from 'node:path'

export const project = '/app/compdocs/gokbey'
export const title = 'Atlas teslim dizini'
export const updatedTitle = 'Atlas teslim dizini · ikinci sürüm'
export const btn = (ctx, name) => ctx.getByRole('button', { name, exact: true })
export const txt = (ctx, value) => ctx.getByText(value, { exact: true })
export const modal = d => d.page.locator('.n-modal:visible').last()
export const drawer = d => d.page.locator('.n-drawer:visible')
export const option = (d, name) => d.page.locator('.n-base-select-option:visible').filter({ hasText: name }).first()
export const input = (container, label) => container.locator('.n-form-item').filter({
  has: container.page().locator('.n-form-item-label').filter({ hasText: new RegExp('^' + label + '\\s*[:*]?\\s*$') })
}).locator('input,textarea').first()
export const beat = (feature, text, action, expected) => ({feature, text, action, expected: expected || text})
export const clickText = (d, scope, text) => d.click(txt(scope, text).first())
export const seen = locator => locator.first().waitFor({state:'visible',timeout:15000})
export const gone = locator => locator.first().waitFor({state:'hidden',timeout:15000})
export const clickButton = (d, name, scope=d.page) => d.click(btn(scope, name).first())
export const file = (d,name,scope=d.page) => d.file(scope.locator('input[type=file]').first(), path.join(d.samples,name))
export const closeModal = async d => {
  const panel = modal(d)
  await d.click(panel.locator('.n-card-header__close,.n-dialog__close').first())
  await gone(panel)
}
export const choose = async(d, control, pattern) => {
  await d.click(control)
  const target = pattern ? option(d,pattern) : d.page.locator('.n-base-select-option:visible:not(.n-base-select-option--disabled)').first()
  await d.click(target)
}
export async function search(d, term) {
  const field = d.page.getByPlaceholder('Search documents')
  await d.fill(field,term)
  await Promise.all([
    d.page.waitForResponse(r=>r.url().includes('/compliance-documents/') &&
      r.request().method()==='GET' && new URL(r.url()).searchParams.get('search')===term,{timeout:30000}),
    field.press('Enter')
  ])
}
export const workspaceRows = d => d.page.locator('tr[aria-label^="Double-click or press Enter"]')
export async function enterRow(d, pattern) {
  let row = workspaceRows(d)
  if (pattern) row=row.filter({hasText:pattern})
  row=row.first()
  await d.click(row)
  await row.press('Enter')
  await seen(drawer(d).locator('.workspace-title'))
}
export const tab = (d, label, scope=drawer(d)) => clickText(d,scope.locator('.n-tabs-nav'),label)
export async function drawerTab(d, label) {
  const drawerPane = drawer(d)
  const target = drawerPane.locator('.workspace-tabs .n-tabs-tab').filter({hasText:label})
  // Naive UI may tuck its last tabs into the overflow menu on narrow drawers.
  if (await target.count() && await target.first().isVisible()) {
    await d.click(target.first())
  } else {
    await d.hover(drawerPane.locator('.n-tabs-nav__suffix,.n-tabs-nav__more,.n-tabs-nav__more-pad').first())
    await clickText(d,d.page.locator('.n-dropdown-menu'),label)
  }
}
export async function ensureJira(d, {showMethods=false}={}) {
  const disconnected = btn(d.page,'Connect')
  const watcher = d.page.locator('.jira-tabs .n-tabs-nav')
  await seen(disconnected.or(watcher.first()))
  if (showMethods && !await disconnected.isVisible()) {
    await clickButton(d,'Disconnect from JIRA')
    await seen(disconnected)
  }
  if (await disconnected.isVisible()) {
    if (showMethods) {
      await d.click(d.page.getByRole('tab',{name:'Personal Access Token'}))
      await seen(d.page.locator('#jira-username'))
      await d.pause(420)
      await d.click(d.page.getByRole('tab',{name:'Session ID'}))
    }
    // The local provider accepts an ephemeral presentation-only string.
    await d.fill(d.page.locator('#jira-credential'), crypto.randomUUID().slice(0,12))
    await d.click(disconnected)
  }
  await seen(d.page.locator('.jira-account-tag'))
}
export async function jiraTab(d, name) {
  await ensureJira(d)
  await clickText(d,d.page.locator('.jira-tabs > .n-tabs > .n-tabs-nav'),name)
}
export async function resultDownload(d, label='Download result') {
  const button = btn(d.page, label).first()
  await button.waitFor({state:'visible',timeout:45000})
  await d.download(()=>d.click(button))
}
