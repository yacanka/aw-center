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

/** Compliance navigation families; entries are joined with the authorized catalog. */
export const COMPLIANCE_PROJECT_GROUPS = [
  { key: 'ozgur', label: 'Özgür', slugs: ['aesa', 'blok30', 'blok4050', 'hys'] },
  { key: 'gokbey', label: 'Gökbey', slugs: ['gokbey', 'gokbey_jandarma'] },
  { key: 'havasoj', label: 'Havasoj', slugs: ['havasoj_stc1', 'havasoj_stc2'] },
  { key: 'hurkus2', label: 'Hürkuş 2', slugs: ['hyeu', 'hurkus_aviyonik'] },
  { key: 'hurjet', label: 'Hürjet', slugs: ['hjt', 'hsp', 'navy'] }
] as const

export const COMPLIANCE_STANDALONE_PROJECTS = ['bkm', 'mmu'] as const

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
