import { API_PATHS } from '@/shared/api/apiPaths'
import { apiClient } from '@/shared/api/http'
import type { Job } from '@/features/jobs/api/jobs'

export type DoorsPosition = 'first' | 'after' | 'before' | 'below' | 'below_last'
export type DoorsScalarAttributes = Record<string, string | number | boolean | null>

export interface DoorsStatus {
  configured: boolean
  available: boolean
  active_agents: number
  transport: 'outbound_https_mtls'
}

export interface DoorsObjectUpdateInput {
  module_path: string
  absolute_number: number
  attributes: DoorsScalarAttributes
}

export interface DoorsObjectCreateInput {
  module_path: string
  position: DoorsPosition
  relative_absolute_number?: number
  attributes: DoorsScalarAttributes
}

export type DoorsLinkDirection = 'ref2tar' | 'tar2ref'

export interface DoorsRequirementLinkInput {
  ref_module_name: string
  target_module_name: string
  link_module_name: string
  ref_attr_poc: string
  ref_attr_req: string
  target_attr_poc: string
  start_index: number
  text_length: number
  direction: DoorsLinkDirection
  activeness: boolean
}

export interface DoorsRequirementLinkGroup {
  poc: string
  requirements: string[]
  target_found: boolean
}

export interface DoorsRequirementLinkResult {
  type: 'doors_requirement_linker'
  schema_version: 1
  mode: 'preview' | 'link'
  direction: DoorsLinkDirection
  summary: {
    reference_objects: number
    groups: number
    candidates: number
    matched_targets: number
    missing_targets: number
    created_links: number
    existing_links: number
  }
  groups: DoorsRequirementLinkGroup[]
  missing_targets: string[]
}

/** Return DOORS feature-flag and live-agent readiness as one fail-closed decision. */
export async function fetchDoorsStatus(): Promise<DoorsStatus> {
  return (await apiClient.get<DoorsStatus>(`${API_PATHS.doors}/status/`)).data
}

/** Queue a module accessibility check for the Windows automation agent. */
export async function enqueueDoorsModuleCheck(
  modulePath: string,
  idempotencyKey: string
): Promise<Job> {
  return enqueueDoorsJob(
    `${API_PATHS.doors}/module-check-jobs/`,
    { module_path: modulePath },
    idempotencyKey
  )
}

/** Queue a bounded module export for compliance field linking and import preview. */
export async function enqueueDoorsModuleExport(
  modulePath: string,
  limit: number,
  idempotencyKey: string
): Promise<Job> {
  return enqueueDoorsJob(
    `${API_PATHS.doors}/module-export-jobs/`,
    { module_path: modulePath, limit },
    idempotencyKey
  )
}

/** Queue a validated scalar update; browser requests never execute COM directly. */
export async function enqueueDoorsObjectUpdate(
  input: DoorsObjectUpdateInput,
  idempotencyKey: string
): Promise<Job> {
  return enqueueDoorsJob(`${API_PATHS.doors}/object-update-jobs/`, input, idempotencyKey)
}

/** Queue a validated object creation; browser requests never execute COM directly. */
export async function enqueueDoorsObjectCreate(
  input: DoorsObjectCreateInput,
  idempotencyKey: string
): Promise<Job> {
  return enqueueDoorsJob(`${API_PATHS.doors}/object-create-jobs/`, input, idempotencyKey)
}

/** Queue the fixed-purpose PoC preview or administrator-authorized link operation. */
export async function enqueueDoorsRequirementLink(
  input: DoorsRequirementLinkInput,
  idempotencyKey: string
): Promise<Job> {
  return enqueueDoorsJob(`${API_PATHS.doors}/requirement-link-jobs/`, input, idempotencyKey)
}

/** Read the SHA-256-verified private JSON result through its owner-only job URL. */
export async function fetchDoorsRequirementLinkResult(
  job: Job
): Promise<DoorsRequirementLinkResult> {
  if (job.kind !== 'doors.link_requirements' || !job.download_url) {
    throw new Error('The Requirement PoC Linker result is unavailable.')
  }
  const response = await apiClient.get<DoorsRequirementLinkResult>(job.download_url, {
    responseType: 'json'
  })
  if (response.data.type !== 'doors_requirement_linker' || response.data.schema_version !== 1) {
    throw new Error('The Requirement PoC Linker returned an unsupported result.')
  }
  return response.data
}

async function enqueueDoorsJob(path: string, input: object, idempotencyKey: string): Promise<Job> {
  const response = await apiClient.post<Job>(path, input, {
    headers: { 'Idempotency-Key': idempotencyKey }
  })
  return response.data
}
