import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '@/app/router/routes'
import { createMainMenuOptions, type ProjectMenuOption } from '@/app/services/mainMenu'
import { resolveAssistantPath } from './navigation'

const router = createRouter({ history: createMemoryHistory('/app/'), routes })
const guideRows = JSON.parse(
  readFileSync(
    new URL('../../../../../backend/integrations/assistant/guide_data.json', import.meta.url),
    'utf8'
  )
) as { id: string; path: string }[]

function leaves(options: ProjectMenuOption[]): string[] {
  return options.flatMap((item) =>
    item.children ? leaves(item.children) : item.type === 'divider' ? [] : [String(item.key)]
  )
}

describe('assistant canonical navigation', () => {
  it('covers exactly the effective menu for an authorized superuser', () => {
    const menu = leaves(
      createMainMenuOptions(
        [
          {
            slug: 'aesa',
            name: 'AESA',
            capabilities: ['compliance', 'dcc', 'organization'],
            roles: { compliance: 'viewer', dcc: 'viewer', organization: 'viewer' }
          }
        ],
        { id: 1, is_superuser: true },
        true,
        true
      )
    )
    const expected = menu.filter((path) => path !== '/compdocs/aesa').sort()
    expect(guideRows.map((entry) => entry.path).sort()).toEqual(expected)
    expect(new Set(guideRows.map((entry) => entry.id)).size).toBe(guideRows.length)
    for (const entry of guideRows) expect(resolveAssistantPath(entry.path, router)).toBe(entry.path)
  })

  it('accepts a canonical dynamic project path', () => {
    expect(resolveAssistantPath('/compdocs/aesa', router)).toBe('/compdocs/aesa')
  })

  it.each([
    '//host/path',
    'https://host/compare',
    '/compare?token=x',
    '/compare#x',
    '/compare\\x',
    '/compare/excel',
    '/outlook',
    '/welcome',
    '/',
    '/missing',
    '/app/compare',
    '/compare/',
    '/%63ompare',
    '/compdocs/../compare',
    '/compdocs/aesa?x=y',
    '/compdocs//aesa',
    '/compare\n'
  ])('rejects unsafe or noncanonical path %s', (path) => {
    expect(resolveAssistantPath(path, router)).toBeNull()
  })
})
