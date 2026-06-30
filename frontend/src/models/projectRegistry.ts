/**
 * Allowed project capabilities shared with the backend registry contract.
 * Adding a capability is a backend/frontend contract change: update
 * backend/projects/constants.py, API/integrity tests, and consumers together.
 */
export const PROJECT_CAPABILITIES = ['dcc', 'compdocs', 'orgs'] as const

export type ProjectCapability = (typeof PROJECT_CAPABILITIES)[number]

export interface ProjectRegistryItem {
  slug: string
  display_name: string
  route: string
  enabled: boolean
  capabilities: ProjectCapability[]
  tags: string[]
}
