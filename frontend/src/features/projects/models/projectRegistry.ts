/**
 * Allowed project capabilities shared with the backend registry contract.
 * Adding a capability is a backend/frontend contract change: update
 * backend/projects/constants.py, API/integrity tests, and consumers together.
 */
export const PROJECT_CAPABILITIES = ['dcc', 'compliance', 'organization'] as const

export type ProjectCapability = (typeof PROJECT_CAPABILITIES)[number]
export type ProjectRole = 'viewer' | 'editor' | 'manager' | 'operator' | 'publisher'
export type ProjectManagementRole = 'viewer' | 'editor' | 'manager'
export type ProjectDccRole = 'viewer' | 'operator' | 'publisher'

export interface ProjectRegistryItem {
  slug: string
  name: string
  capabilities: ProjectCapability[]
  roles: Record<ProjectCapability, ProjectRole | null>
}

const MANAGEMENT_ROLE_RANK: Record<ProjectManagementRole, number> = {
  viewer: 1,
  editor: 2,
  manager: 3
}

const DCC_ROLE_RANK: Record<ProjectDccRole, number> = {
  viewer: 1,
  operator: 2,
  publisher: 3
}

/** Compare project-domain roles without reusing unrelated Django model permissions. */
export function hasProjectManagementRole(
  role: ProjectRole | null | undefined,
  minimum: ProjectManagementRole
): boolean {
  if (!role || !(role in MANAGEMENT_ROLE_RANK)) return false
  return MANAGEMENT_ROLE_RANK[role as ProjectManagementRole] >= MANAGEMENT_ROLE_RANK[minimum]
}

/** Compare roles only within the DCC authorization hierarchy. */
export function hasProjectDccRole(
  role: ProjectRole | null | undefined,
  minimum: ProjectDccRole
): boolean {
  if (!role || !(role in DCC_ROLE_RANK)) return false
  return DCC_ROLE_RANK[role as ProjectDccRole] >= DCC_ROLE_RANK[minimum]
}
