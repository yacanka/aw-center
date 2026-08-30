import { describe, expect, it, vi } from 'vitest'

vi.mock('@/shared/api/http', () => ({ apiClient: { get: vi.fn() } }))

import { parseProjectRegistryItems } from '@/features/projects/api/projectRegistry'
import { hasProjectManagementRole } from '@/features/projects/models/projectRegistry'

const project = {
  slug: 'ozgur',
  name: 'Özgür',
  capabilities: ['compliance', 'organization'],
  roles: { compliance: 'editor', organization: 'viewer', dcc: null }
}

describe('project registry fail-closed parsing', () => {
  it('accepts a valid empty catalog without synthesizing projects', () => {
    expect(parseProjectRegistryItems([], 'compliance')).toEqual([])
  })

  it('filters capability-less projects', () => {
    expect(
      parseProjectRegistryItems(
        [
          project,
          {
            ...project,
            slug: 'dcc',
            capabilities: ['dcc'],
            roles: { compliance: null, organization: null, dcc: 'viewer' }
          }
        ],
        'compliance'
      )
    ).toEqual([project])
  })

  it('filters projects for which the server granted no role', () => {
    expect(
      parseProjectRegistryItems(
        [{ ...project, roles: { ...project.roles, compliance: null } }],
        'compliance'
      )
    ).toEqual([])
  })

  it('rejects malformed responses instead of granting fallback capabilities', () => {
    expect(() => parseProjectRegistryItems({ results: [project] }, 'compliance')).toThrow(/invalid/)
    expect(() => parseProjectRegistryItems([{ ...project, roles: {} }], 'compliance')).toThrow(
      /invalid item/
    )
  })

  it('compares only roles in the management hierarchy', () => {
    expect(hasProjectManagementRole('manager', 'editor')).toBe(true)
    expect(hasProjectManagementRole('viewer', 'editor')).toBe(false)
    expect(hasProjectManagementRole('publisher', 'viewer')).toBe(false)
  })
})
