/**
 * Allowed project capabilities shared with the backend registry contract.
 * Adding a capability is a backend/frontend contract change: update
 * backend/projects/constants.py, API/integrity tests, and consumers together.
 */
export const PROJECT_CAPABILITIES = ['jira', 'compliance', 'organization'] as const

export type ProjectCapability = (typeof PROJECT_CAPABILITIES)[number]
export type ProjectRole = 'viewer' | 'editor' | 'manager' | 'operator' | 'publisher'
export type ProjectManagementRole = 'viewer' | 'editor' | 'manager'
export type ProjectJiraRole = 'viewer' | 'operator' | 'publisher'

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

const JIRA_ROLE_RANK: Record<ProjectJiraRole, number> = {
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
export function hasProjectJiraRole(
  role: ProjectRole | null | undefined,
  minimum: ProjectJiraRole
): boolean {
  if (!role || !(role in JIRA_ROLE_RANK)) return false
  return JIRA_ROLE_RANK[role as ProjectJiraRole] >= JIRA_ROLE_RANK[minimum]
}
