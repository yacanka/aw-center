import { apiClient } from '@/shared/api/http'
import { compdocCollectionPath } from '@/shared/api/apiPaths'
import type { CompDocCreatePayload } from '@/features/compliance/api/compdocPayload'
import type { Job } from '@/features/jobs/api/jobs'
export interface NumberingOptions {
  provider: 'numarator'
  available: boolean
  supports: string[]
  formats: string[]
}

export interface CoverPageAllocation {
  id: string
  version: number
  status: 'requested' | 'allocated' | 'use_pending' | 'completed' | 'reconciliation_required'
  number: string
  format_code: string
  context_data?: Record<string, string | number | boolean>
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
  document: CompDocCreatePayload,
  documentId?: string,
  formatCode?: string,
  contextData: Record<string, string> = {}
): Promise<CoverPageAllocation> {
  const response = await apiClient.post<CoverPageAllocation>(allocationPath(project), {
    client_operation_id: clientOperationId,
    document,
    context_data: contextData,
    ...(formatCode ? { format_code: formatCode } : {}),
    ...(documentId ? { document_id: documentId } : {})
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

export async function fetchExistingCoverPageAllocation(
  project: string,
  documentId: string
): Promise<CoverPageAllocation | null> {
  const response = await apiClient.get<{ allocation: CoverPageAllocation | null }>(
    allocationPath(project),
    { params: { document_id: documentId } }
  )
  return response.data.allocation
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

export interface NumberingContextField {
  key: string
  required: boolean
  default: string | number | boolean | null
  max_length: number
}
export interface NumberingFormat {
  schema_version: number
  code: string
  fields: NumberingContextField[]
}

/** Discover format inputs through the worker; credentials never enter the web process. */
export async function fetchNumberingFormat(
  project: string,
  code: string,
  signal: AbortSignal
): Promise<NumberingFormat> {
  const { data: initial } = await apiClient.post<Job>(
    `${compdocCollectionPath(project)}numbering-options/`,
    {
      client_operation_id: crypto.randomUUID(),
      format_code: code
    },
    { signal }
  )
  let job = initial
  const deadline = Date.now() + 90_000
  while (['queued', 'running'].includes(job.status)) {
    if (Date.now() >= deadline)
      throw new Error('Number format loading timed out. Check the worker and retry.')
    await new Promise<void>((resolve, reject) => {
      if (signal.aborted) {
        reject(new Error('Cancelled'))
        return
      }
      const abort = () => {
        clearTimeout(timer)
        reject(new Error('Cancelled'))
      }
      const timer = setTimeout(() => {
        signal.removeEventListener('abort', abort)
        resolve()
      }, 1000)
      signal.addEventListener('abort', abort, { once: true })
    })
    job = (await apiClient.get<Job>(`jobs/${job.id}/`, { signal })).data
  }
  if (job.status !== 'succeeded' || !job.download_url) {
    throw new Error(job.message || 'Number format fields could not be loaded.')
  }
  const { data } = await apiClient.get<NumberingFormat>(job.download_url, {
    responseType: 'json',
    signal
  })
  if (data.schema_version !== 1 || data.code !== code || !Array.isArray(data.fields)) {
    throw new Error('The number format response is invalid.')
  }
  return data
}
