import axios from 'axios'
import type { InvalidDocument } from '@/models/compdocs'

export interface ImportMappingRow {
  source: string
  target: string
}

export interface ImportInvalidDocument extends InvalidDocument {
  name: string
  error: unknown
  error_text?: string
  row?: number
}

export interface ImportPreview {
  header_row: number
  mapped_columns: ImportMappingRow[]
  unmapped_columns: string[]
  missing_columns: string[]
  invalid_documents: ImportInvalidDocument[]
  created_count: number
  updated_count: number
  unchanged_count: number
  rejected_count: number
  confirmation_token: string
}

export interface ImportResult {
  message: string
  invalid_documents: ImportInvalidDocument[]
}

/** Inspect one workbook without changing compliance-document persistence. */
export async function previewCompdocImport(uploadUrl: string, file: File) {
  const response = await axios.post<ImportPreview>(`${uploadUrl}?preview=true`, formData(file))
  return response.data
}

/** Apply only the exact workbook approved by its signed preview token. */
export async function confirmCompdocImport(
  uploadUrl: string,
  file: File,
  confirmationToken: string
) {
  const response = await axios.post<ImportResult>(
    `${uploadUrl}?confirm_import=true`,
    formData(file, confirmationToken)
  )
  return response.data
}

function formData(file: File, confirmationToken?: string) {
  const data = new FormData()
  data.append('file', file)
  if (confirmationToken) data.append('confirmation_token', confirmationToken)
  return data
}
