import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))

import { fetchPanels, fetchResponsibles } from '@/features/organization/api/organizationProjects'
import { createOrganizationState } from '@/features/organization/composables/organizationState'

describe('organization project API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('filters responsible assignments by panel ID when chapters can be empty', async () => {
    http.get.mockResolvedValueOnce({
      status: 200,
      data: { count: 1, next: null, previous: null, results: [{ id: 3, panel: 11 }] }
    })
    const state = createOrganizationState()
    state.project = 'demo'
    await fetchResponsibles(state, '11')
    expect(http.get).toHaveBeenCalledWith('projects/demo/organization/responsible-assignments/', {
      params: { panel_id: '11', page_size: 200 }
    })
    expect(state.responsibles).toEqual([{ id: 3, panel: 11 }])
  })

  it('stores panel rows returned across paginated responses', async () => {
    http.get
      .mockResolvedValueOnce({
        status: 200,
        data: {
          count: 2,
          next: '/api/projects/demo/organization/panels/?page=2',
          previous: null,
          results: [{ id: 1, project_slug: 'demo', name: 'Avionics', ata: '23' }]
        }
      })
      .mockResolvedValueOnce({
        status: 200,
        data: {
          count: 2,
          next: null,
          previous: '/api/projects/demo/organization/panels/',
          results: [{ id: 2, project_slug: 'demo', name: 'Electrical', ata: '24' }]
        }
      })
    const state = createOrganizationState()
    state.project = 'demo'

    await fetchPanels(state)

    expect(state.panels).toEqual([
      { id: 1, project_slug: 'demo', project: 'demo', name: 'Avionics', ata: '23' },
      { id: 2, project_slug: 'demo', project: 'demo', name: 'Electrical', ata: '24' }
    ])
    expect(http.get).toHaveBeenNthCalledWith(1, 'projects/demo/organization/panels/', {
      params: { page_size: 200 }
    })
    expect(http.get).toHaveBeenNthCalledWith(2, '/api/projects/demo/organization/panels/?page=2', {
      params: undefined
    })
  })
})
