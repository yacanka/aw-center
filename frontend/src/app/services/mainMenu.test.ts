import { describe, expect, it } from 'vitest'
import { createMainMenuOptions, type ProjectMenuOption } from '@/app/services/mainMenu'
import type { ProjectRegistryItem } from '@/features/projects/models/projectRegistry'

const user = { id: 1, is_active: true, is_staff: true }
const project: ProjectRegistryItem = {
  slug: 'ozgur',
  name: 'Özgür',
  capabilities: ['compliance', 'organization', 'jira'],
  roles: { compliance: 'viewer', organization: 'viewer', jira: 'viewer' }
}

describe('project-aware main navigation', () => {
  it('offers Mermaid to authenticated users immediately after Translator without project roles', () => {
    const options = createMainMenuOptions([], { id: 2, is_active: true })
    const translator = options.findIndex((option) => option.key === '/translator')
    expect(options[translator + 1]).toMatchObject({ key: '/mermaid', label: 'Mermaid Atölyesi' })
    expect(menuKeys(createMainMenuOptions([], {}))).not.toContain('/mermaid')
  })
  it('keeps project domains hidden until the authorized catalog is ready', () => {
    const options = createMainMenuOptions([], user, false, false)
    const keys = menuKeys(options)

    expect(keys).not.toContain('/settings')
    expect(keys).not.toContain('/compdocs/home')
    expect(keys).not.toContain('/organization')
    expect(keys).not.toContain('/jira')
    expect(keys).toContain('/jira/documents')
    expect(options.find((option) => option.label === 'JIRA')?.children).toMatchObject([
      { key: '/jira/documents', label: 'Documents' }
    ])
    expect(menuKeys(createMainMenuOptions([], {}))).not.toContain('/jira/documents')
  })

  it('shows only domains backed by validated catalog roles', () => {
    const options = createMainMenuOptions([project], user, true, true)
    const keys = menuKeys(options)

    expect(keys).toContain('/compdocs/home')
    expect(keys).not.toContain('/compdocs/ozgur')
    expect(keys).toContain('/organization')
    expect(keys).toContain('/jira')
    expect(options.find((option) => option.label === 'JIRA')?.children).toMatchObject([
      { key: '/jira', label: 'Workspace' },
      { key: '/jira/documents', label: 'Documents' }
    ])
  })
})

function menuKeys(options: ProjectMenuOption[]): string[] {
  return options.flatMap((option) => [String(option.key || ''), ...menuKeys(option.children || [])])
}
