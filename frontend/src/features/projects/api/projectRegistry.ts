import { apiClient as axios } from '@/shared/api/http'
import {
  PROJECT_CAPABILITIES,
  type ProjectCapability,
  type ProjectRegistryItem
} from '@/features/projects/models/projectRegistry'

/** Fetch all project entries for which the authenticated user has a domain role. */
export async function fetchProjectRegistry(): Promise<ProjectRegistryItem[]> {
  const response = await axios.get<unknown>('projects/')
  return parseProjectRegistryItems(response.data)
}

export function parseProjectRegistryItems(
  data: unknown,
  capability?: ProjectCapability
): ProjectRegistryItem[] {
  if (!Array.isArray(data)) throw new Error('The project catalog response is invalid.')

  if (!data.every(isProjectRegistryItem)) {
    throw new Error('The project catalog contains an invalid item.')
  }

  return data.filter((project) =>
    capability
      ? project.capabilities.includes(capability) && project.roles[capability] !== null
      : project.capabilities.some((item) => project.roles[item] !== null)
  )
}

function isProjectRegistryItem(item: unknown): item is ProjectRegistryItem {
  if (!isRecord(item)) return false
  const capabilities = item.capabilities
  const roles = item.roles
  if (
    typeof item.slug !== 'string' ||
    !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(item.slug) ||
    typeof item.name !== 'string' ||
    !item.name.trim() ||
    item.name.length > 200 ||
    !isProjectCapabilityArray(capabilities) ||
    !isProjectRoles(roles)
  ) {
    return false
  }

  return PROJECT_CAPABILITIES.every(
    (capability) => roles[capability] === null || capabilities.includes(capability)
  )
}

function isRecord(item: unknown): item is Record<string, unknown> {
  return Object.prototype.toString.call(item) === '[object Object]'
}

function isProjectCapabilityArray(item: unknown): item is ProjectCapability[] {
  return (
    Array.isArray(item) &&
    item.length > 0 &&
    new Set(item).size === item.length &&
    item.every(isProjectCapability)
  )
}

function isProjectCapability(item: unknown): item is ProjectCapability {
  return typeof item === 'string' && PROJECT_CAPABILITIES.includes(item as ProjectCapability)
}

function isProjectRoles(item: unknown): item is ProjectRegistryItem['roles'] {
  if (!isRecord(item)) return false
  return (
    [null, 'viewer', 'editor', 'manager'].includes(item.compliance as string | null) &&
    [null, 'viewer', 'manager'].includes(item.organization as string | null) &&
    [null, 'viewer', 'operator', 'publisher'].includes(item.dcc as string | null)
  )
}
