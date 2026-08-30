import { apiClient as axios } from '@/shared/api/http'
import type { InvalidDocument } from '@/features/compliance/models/compdocs'

export interface ImportMappingRow {
  source: string
  target: string
}

export interface ImportInvalidDocument extends InvalidDocument {
  row?: number
  code: string
  fields: Record<string, unknown>
}

export interface ImportPreview {
  header_row: number | null
  mapped_columns: ImportMappingRow[]
  unmapped_columns: string[]
  missing_columns: string[]
  invalid_documents: ImportInvalidDocument[]
  created_count: number
  updated_count: number
  unchanged_count: number
  rejected_count: number
  confirmation_token: string
  database_state_protected: boolean
}

export interface ImportResult {
  detail: string
  code: string
  audit_id: string
  status: 'success' | 'partial' | 'failed'
  created_count: number
  updated_count: number
  unchanged_count: number
  rejected_count: number
  invalid_documents: ImportInvalidDocument[]
}

export interface DoorsImportTargetField {
  key: string
  label: string
  required: boolean
}

export interface DoorsImportSource {
  job_id: string
  module_path: string
  row_count: number
  columns: string[]
  default_mapping: Record<string, string>
  target_fields: DoorsImportTargetField[]
}

export interface DoorsImportPreview extends ImportPreview {
  job_id: string
  module_path: string
}

/** Inspect one workbook without changing compliance-document persistence. */
export async function previewCompdocImport(collectionPath: string, file: File) {
  const response = await axios.post<ImportPreview>(
    `${collectionPath}imports/preview/`,
    formData(file)
  )
  return response.data
}

/** Apply only the exact workbook approved by its signed preview token. */
export async function confirmCompdocImport(
  collectionPath: string,
  file: File,
  confirmationToken: string
) {
  const response = await axios.post<ImportResult>(
    `${collectionPath}imports/confirm/`,
    formData(file, confirmationToken)
  )
  return response.data
}

/** Load verified DOORS source metadata without exposing its private job artifact. */
export async function fetchDoorsImportSource(collectionPath: string, jobId: string) {
  const response = await axios.get<DoorsImportSource>(
    `${collectionPath}imports/doors/sources/${jobId}/`
  )
  return response.data
}

/** Apply the canonical compliance validations to one DOORS field mapping. */
export async function previewDoorsImport(
  collectionPath: string,
  jobId: string,
  mapping: Record<string, string>
) {
  const response = await axios.post<DoorsImportPreview>(`${collectionPath}imports/doors/preview/`, {
    job_id: jobId,
    mapping
  })
  return response.data
}

/** Confirm only the DOORS source, mapping, and database state shown in preview. */
export async function confirmDoorsImport(
  collectionPath: string,
  jobId: string,
  mapping: Record<string, string>,
  confirmationToken: string
) {
  const response = await axios.post<ImportResult>(`${collectionPath}imports/doors/confirm/`, {
    job_id: jobId,
    mapping,
    confirmation_token: confirmationToken
  })
  return response.data
}

function formData(file: File, confirmationToken?: string) {
  const data = new FormData()
  data.append('file', file)
  if (confirmationToken) data.append('confirmation_token', confirmationToken)
  return data
}
