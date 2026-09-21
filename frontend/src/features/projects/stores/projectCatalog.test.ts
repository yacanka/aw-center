import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/features/projects/api/projectRegistry', () => ({ fetchProjectRegistry: vi.fn() }))

import { fetchProjectRegistry } from '@/features/projects/api/projectRegistry'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import type { ProjectRegistryItem } from '@/features/projects/models/projectRegistry'

const dccProject: ProjectRegistryItem = {
  slug: 'ozgur',
  name: 'Özgür',
  capabilities: ['dcc'],
  roles: { compliance: null, organization: null, dcc: 'operator' }
}

describe('project catalog authorization state', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('keeps all capability decisions closed when catalog loading fails', async () => {
    vi.mocked(fetchProjectRegistry).mockRejectedValue(new Error('offline'))
    const catalog = useProjectCatalogStore()

    await expect(catalog.load()).rejects.toThrow('offline')

    expect(catalog.status).toBe('error')
    expect(catalog.projects).toEqual([])
    expect(catalog.hasAnyRole('dcc')).toBe(false)
  })

  it('opens a capability only after a validated server role is ready', async () => {
    vi.mocked(fetchProjectRegistry).mockResolvedValue([dccProject])
    const catalog = useProjectCatalogStore()

    expect(catalog.hasAnyRole('dcc')).toBe(false)
    await catalog.load()

    expect(catalog.status).toBe('ready')
    expect(catalog.hasAnyRole('dcc')).toBe(true)
  })

  it('accepts new DCC projects without granting unrelated capabilities', async () => {
    vi.mocked(fetchProjectRegistry).mockResolvedValue([
      { ...dccProject, slug: 'hurkus', name: 'Hürkuş' },
      { ...dccProject, slug: 'gokbey_sivil', name: 'Gökbey Sivil' },
      { ...dccProject, slug: 'gokbey_jandarma', name: 'Gökbey Jandarma' }
    ])
    const catalog = useProjectCatalogStore()
    await catalog.load()

    expect(catalog.projects.map((project) => project.slug)).toEqual([
      'hurkus',
      'gokbey_sivil',
      'gokbey_jandarma'
    ])
    expect(catalog.hasAnyRole('dcc')).toBe(true)
    expect(catalog.hasAnyRole('compliance')).toBe(false)
    expect(catalog.hasAnyRole('organization')).toBe(false)
  })

  it('does not repopulate account data when an in-flight request resolves after clear', async () => {
    let resolveRequest: (projects: ProjectRegistryItem[]) => void = () => undefined
    vi.mocked(fetchProjectRegistry).mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve
      })
    )
    const catalog = useProjectCatalogStore()

    const request = catalog.load()
    catalog.clear()
    resolveRequest([dccProject])
    await request

    expect(catalog.status).toBe('unknown')
    expect(catalog.projects).toEqual([])
    expect(catalog.hasAnyRole('dcc')).toBe(false)
  })
})
