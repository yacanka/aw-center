import { API_PATHS } from '@/shared/api/apiPaths'
import { apiClient } from '@/shared/api/http'
import type { Job } from '@/features/jobs/api/jobs'

export type DoorsPosition = 'first' | 'after' | 'before' | 'below' | 'below_last'
export type DoorsScalarAttributes = Record<string, string | number | boolean | null>

export interface DoorsOperationMetadata {
  schema_version: 1
  operation: 'check_module' | 'update_object' | 'create_object'
  outcome: 'success' | 'negative'
  code: string
  message: string
  input: Record<string, unknown> & { module_path: string }
}

export interface DoorsDeveloperResult {
  operation_result: DoorsOperationMetadata
  accessible?: boolean
  updated?: boolean
  absolute_number?: number
  identifier?: string
  [key: string]: unknown
}

export interface DoorsStatus {
  configured: boolean
  available: boolean
  active_workers: number
  transport: 'windows-worker'
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

/** Return DOORS feature-flag and Windows-worker readiness as one fail-closed decision. */
export async function fetchDoorsStatus(): Promise<DoorsStatus> {
  return (await apiClient.get<DoorsStatus>(`${API_PATHS.doors}/status/`)).data
}

/** Read a completed operation's versioned result from its verified private artifact. */
export async function fetchDoorsDeveloperResult(job: Job): Promise<DoorsDeveloperResult> {
  const operations: Record<string, DoorsOperationMetadata['operation']> = {
    'doors.run_dxl': 'check_module',
    'doors.update_object': 'update_object',
    'doors.create_object': 'create_object'
  }
  const operation = operations[job.kind]
  if (!operation || job.status !== 'succeeded' || !job.download_url) {
    throw new Error('The DOORS operation result is unavailable.')
  }
  const { data } = await apiClient.get<unknown>(job.download_url, { responseType: 'json' })
  if (!isDeveloperResult(data, operation)) {
    throw new Error('The DOORS operation returned an unsupported or invalid result.')
  }
  return data
}

function isDeveloperResult(
  value: unknown,
  operation: DoorsOperationMetadata['operation']
): value is DoorsDeveloperResult {
  if (!isRecord(value) || !isRecord(value.operation_result)) return false
  const metadata = value.operation_result
  if (
    metadata.schema_version !== 1 ||
    metadata.operation !== operation ||
    typeof metadata.message !== 'string' ||
    !metadata.message ||
    !isRecord(metadata.input) ||
    typeof metadata.input.module_path !== 'string' ||
    !metadata.input.module_path
  )
    return false
  if (operation === 'check_module') {
    return (
      (value.accessible === true &&
        metadata.outcome === 'success' &&
        metadata.code === 'MODULE_OPENED') ||
      (value.accessible === false &&
        metadata.outcome === 'negative' &&
        metadata.code === 'OPEN_MODULE')
    )
  }
  return (
    metadata.outcome === 'success' &&
    Number.isSafeInteger(value.absolute_number) &&
    Number(value.absolute_number) > 0 &&
    (operation === 'create_object'
      ? metadata.code === 'OBJECT_CREATED'
      : metadata.code === 'ATTRIBUTES_SAVED' &&
        value.updated === true &&
        metadata.input.absolute_number === value.absolute_number)
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/** Queue a module accessibility check for the Windows DOORS worker. */
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
