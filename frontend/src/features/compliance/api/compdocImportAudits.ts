import { apiClient as axios } from '@/shared/api/http'
import { compdocCollectionPath } from '@/shared/api/apiPaths'

export type ImportAuditStatus = 'processing' | 'success' | 'partial' | 'failed'

export interface ImportAudit {
  id: string
  project: number
  source_filename: string
  imported_by: number
  status: ImportAuditStatus
  total_rows: number
  created_count: number
  updated_count: number
  unchanged_count: number
  rejected_count: number
  started_at: string
  completed_at: string | null
  duration_ms: number | null
}

export interface ImportAuditError {
  row?: number
  name?: string
  code: string
  detail: string
  fields?: Record<string, string[]>
}

export interface ImportAuditDetail extends ImportAudit {
  source_size: number
  source_sha256: string
  request_id: string
  header_row: number | null
  mapped_columns: Array<{ source: string; target: string }>
  unmapped_columns: string[]
  missing_columns: string[]
  error_summary: ImportAuditError[]
}

export interface ImportAuditPage {
  count: number
  next: string | null
  previous: string | null
  results: ImportAudit[]
}

export interface ImportAuditFilters {
  project: string
  page: number
  page_size: number
  search?: string
  status?: ImportAuditStatus
}

/** Return a project-scoped, paginated CompDoc import audit ledger. */
export async function listImportAudits(filters: ImportAuditFilters): Promise<ImportAuditPage> {
  const { project, ...query } = filters
  const response = await axios.get<ImportAuditPage>(
    `${compdocCollectionPath(project)}import-audits/`,
    {
      params: query
    }
  )
  return response.data
}

/** Return sanitized mapping and row-error evidence for one project import audit. */
export async function getImportAudit(project: string, auditId: string): Promise<ImportAuditDetail> {
  const response = await axios.get<ImportAuditDetail>(
    `${compdocCollectionPath(project)}import-audits/${encodeURIComponent(auditId)}/`
  )
  return response.data
}
