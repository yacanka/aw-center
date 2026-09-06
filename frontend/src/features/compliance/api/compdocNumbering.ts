import { apiClient } from '@/shared/api/http'
import { compdocCollectionPath } from '@/shared/api/apiPaths'
import type { CompDocCreatePayload } from '@/features/compliance/api/compdocPayload'
import type { Job } from '@/features/jobs/api/jobs'

export interface NumberingOptions {
  provider: 'numarator'
  available: boolean
  supports: string[]
}

export interface CoverPageAllocation {
  id: string
  version: number
  status: 'requested' | 'allocated' | 'use_pending' | 'completed' | 'reconciliation_required'
  number: string
  error_code: string
  error_detail: string
  job: Job | null
  document: unknown | null
  created_at: string
  updated_at: string
}

function allocationPath(project: string, allocationId = ''): string {
  return `${compdocCollectionPath(project)}number-allocations/${allocationId ? `${encodeURIComponent(allocationId)}/` : ''}`
}

export async function fetchNumberingOptions(project: string): Promise<NumberingOptions> {
  const response = await apiClient.get<NumberingOptions>(
    `${compdocCollectionPath(project)}numbering-options/`
  )
  return response.data
}

export async function createCoverPageAllocation(
  project: string,
  clientOperationId: string,
  document: CompDocCreatePayload
): Promise<CoverPageAllocation> {
  const response = await apiClient.post<CoverPageAllocation>(allocationPath(project), {
    client_operation_id: clientOperationId,
    document
  })
  return response.data
}

export async function fetchCoverPageAllocation(
  project: string,
  allocationId: string
): Promise<CoverPageAllocation> {
  const response = await apiClient.get<CoverPageAllocation>(allocationPath(project, allocationId))
  return response.data
}

export async function resumeCoverPageAllocation(
  project: string,
  allocation: CoverPageAllocation
): Promise<CoverPageAllocation> {
  const response = await apiClient.post<CoverPageAllocation>(
    `${allocationPath(project, allocation.id)}resume/`,
    { version: allocation.version }
  )
  return response.data
}
