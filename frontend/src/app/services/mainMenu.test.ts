import { describe, expect, it } from 'vitest'
import { createMainMenuOptions, type ProjectMenuOption } from '@/app/services/mainMenu'
import type { ProjectRegistryItem } from '@/features/projects/models/projectRegistry'

const user = { id: 1, is_active: true, is_staff: true }
const project: ProjectRegistryItem = {
  slug: 'ozgur',
  name: 'Özgür',
  capabilities: ['compliance', 'organization', 'dcc'],
  roles: { compliance: 'viewer', organization: 'viewer', dcc: 'viewer' }
}

describe('project-aware main navigation', () => {
  it('keeps project domains hidden until the authorized catalog is ready', () => {
    const keys = menuKeys(createMainMenuOptions([], user, false, false))

    expect(keys).not.toContain('/compdocs')
    expect(keys).not.toContain('/organization')
    expect(keys).not.toContain('/jira')
  })

  it('shows only domains backed by validated catalog roles', () => {
    const keys = menuKeys(createMainMenuOptions([project], user, true, true))

    expect(keys).toContain('/compdocs')
    expect(keys).toContain('/compdocs/ozgur')
    expect(keys).toContain('/organization')
    expect(keys).toContain('/jira')
  })
})

function menuKeys(options: ProjectMenuOption[]): string[] {
  return options.flatMap((option) => [String(option.key || ''), ...menuKeys(option.children || [])])
}
