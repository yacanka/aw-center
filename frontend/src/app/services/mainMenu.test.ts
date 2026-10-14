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
  it('keeps project domains hidden until the authorized catalog is ready', () => {
    const keys = menuKeys(createMainMenuOptions([], user, false, false))

    expect(keys).not.toContain('/settings')
    expect(keys).not.toContain('/compdocs')
    expect(keys).not.toContain('/organization')
    expect(keys).not.toContain('/jira')
  })

  it('shows only domains backed by validated catalog roles', () => {
    const keys = menuKeys(createMainMenuOptions([project], user, true, true))

    expect(keys).toContain('/compdocs')
    expect(keys).not.toContain('/compdocs/ozgur')
    expect(keys).toContain('/organization')
    expect(keys).toContain('/jira')
  })

  it('groups compliance projects in the requested order with BKM and MMU as direct links', () => {
    const slugs = [
      'mmu',
      'navy',
      'hsp',
      'hjt',
      'hurkus_aviyonik',
      'hyeu',
      'havasoj_stc2',
      'havasoj_stc1',
      'gokbey_jandarma',
      'gokbey',
      'hys',
      'blok4050',
      'blok30',
      'aesa',
      'bkm',
      'ozgur',
      'piku',
      'havasoj',
      'hurjet',
      'gokbey_sivil'
    ]
    const projects = slugs.map((slug) => ({ ...project, slug, name: slug.toUpperCase() }))
    const compliance = createMainMenuOptions(projects, user).find(
      (option) => option.key === '/compdocs'
    )!
    const entries = (compliance.children as ProjectMenuOption[]).filter(
      (option) => option.children || ['/compdocs/bkm', '/compdocs/mmu'].includes(String(option.key))
    )

    expect(entries.map((entry) => entry.label)).toEqual([
      'Özgür',
      'Gökbey',
      'Havasoj',
      'Hürkuş 2',
      'Hürjet',
      'BKM',
      'MMU'
    ])
    expect(entries.map((entry) => entry.children?.map((child) => child.name))).toEqual([
      ['aesa', 'blok30', 'blok4050', 'hys'],
      ['gokbey', 'gokbey_jandarma'],
      ['havasoj_stc1', 'havasoj_stc2'],
      ['hyeu', 'hurkus_aviyonik'],
      ['hjt', 'hsp', 'navy'],
      undefined,
      undefined
    ])
    for (const key of [
      '/compdocs/ozgur',
      '/compdocs/piku',
      '/compdocs/havasoj',
      '/compdocs/hurjet',
      '/compdocs/gokbey_sivil'
    ]) {
      expect(menuKeys(compliance.children!)).not.toContain(key)
    }
  })

  it('omits empty groups and includes only authorized children', () => {
    const projects = ['hys', 'mmu'].map((slug) => ({ ...project, slug, name: slug.toUpperCase() }))
    const compliance = createMainMenuOptions(projects, user).find(
      (option) => option.key === '/compdocs'
    )!
    const groups = (compliance.children as ProjectMenuOption[]).filter((option) => option.children)

    expect(groups.map((group) => group.label)).toEqual(['Özgür'])
    expect(groups[0].children!.map((child) => child.key)).toEqual(['/compdocs/hys'])
    expect(menuKeys(compliance.children!)).not.toContain('/compdocs/aesa')
    expect(menuKeys(compliance.children!)).not.toContain('/compdocs/bkm')
    expect(menuKeys(compliance.children!)).toContain('/compdocs/mmu')
  })
})

function menuKeys(options: ProjectMenuOption[]): string[] {
  return options.flatMap((option) => [String(option.key || ''), ...menuKeys(option.children || [])])
}
