import axios from 'axios'
import {
  PROJECT_CAPABILITIES,
  type ProjectCapability,
  type ProjectRegistryItem
} from '@/models/projectRegistry'

export const PROJECT_REGISTRY_FALLBACK: ProjectRegistryItem[] = [
  createFallbackProject('ozgur', 'Özgür-1', true),
  createFallbackProject('blok30', 'Blok 30', true),
  createFallbackProject('blok4050', 'Blok 40/50', false),
  createFallbackProject('aesa', 'AESA', true),
  createFallbackProject('hys', 'HYS', true),
  createFallbackProject('piku', 'Piku', true),
  createFallbackProject('gokbey', 'Gokbey', false),
  createFallbackProject('havasoj', 'Havasoj', true)
]

/** Fetches frontend-safe project registry items for compliance-document screens. */
export async function fetchCompdocProjectRegistry(): Promise<ProjectRegistryItem[]> {
  return fetchProjectRegistryByCapability('compdocs')
}

/** Fetches active project registry items that support DCC workflows. */
export async function fetchDccProjectRegistry(): Promise<ProjectRegistryItem[]> {
  return fetchProjectRegistryByCapability('dcc')
}

async function fetchProjectRegistryByCapability(
  capability: ProjectCapability
): Promise<ProjectRegistryItem[]> {
  const response = await axios.get<unknown>(
    `/projects/registry/?capability=${capability}&enabled=true`
  )
  return parseProjectRegistryItems(response.data, capability)
}

function createFallbackProject(
  slug: string,
  displayName: string,
  enabled: boolean
): ProjectRegistryItem {
  return {
    slug,
    display_name: displayName,
    route: `/${slug}/`,
    enabled,
    capabilities: ['compdocs', 'dcc', 'orgs'],
    tags: enabled ? ['fallback', 'active'] : ['fallback', 'inactive']
  }
}

function parseProjectRegistryItems(
  data: unknown,
  capability: ProjectCapability = 'compdocs'
): ProjectRegistryItem[] {
  const fallback = PROJECT_REGISTRY_FALLBACK.filter((item) =>
    item.capabilities.includes(capability)
  )
  if (!Array.isArray(data)) return fallback

  const projects = data.filter(isProjectRegistryItem)
  return projects.length > 0 ? projects : fallback
}

function isProjectRegistryItem(item: unknown): item is ProjectRegistryItem {
  if (!isRecord(item)) return false

  return (
    typeof item.slug === 'string' &&
    typeof item.display_name === 'string' &&
    typeof item.route === 'string' &&
    typeof item.enabled === 'boolean' &&
    isProjectCapabilityArray(item.capabilities) &&
    isStringArray(item.tags)
  )
}

function isRecord(item: unknown): item is Record<string, unknown> {
  return Object.prototype.toString.call(item) === '[object Object]'
}

function isProjectCapabilityArray(item: unknown): item is ProjectCapability[] {
  return Array.isArray(item) && item.every(isProjectCapability)
}

function isProjectCapability(item: unknown): item is ProjectCapability {
  return typeof item === 'string' && PROJECT_CAPABILITIES.includes(item as ProjectCapability)
}

function isStringArray(item: unknown): item is string[] {
  return Array.isArray(item) && item.every((value) => typeof value === 'string')
}
