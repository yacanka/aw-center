import { apiClient as axios } from '@/shared/api/http'
import { organizationPath } from '@/shared/api/apiPaths'

export interface PanelImportMapping {
  source: string
  target: 'panel' | 'ata'
}

export interface InvalidPanelImportRow {
  row: number
  code: string
  fields: Record<string, unknown>
}

export interface PanelImportPreview {
  header_row: number
  mapped_columns: PanelImportMapping[]
  unmapped_columns: string[]
  missing_columns: string[]
  invalid_panels: InvalidPanelImportRow[]
  created_count: number
  updated_count: number
  unchanged_count: number
  rejected_count: number
  confirmation_token: string
  database_state_protected: boolean
}

export interface PanelImportResult {
  detail: string
  code: 'PANEL_IMPORT_COMPLETED'
  invalid_panels: InvalidPanelImportRow[]
  created_count: number
  updated_count: number
  unchanged_count: number
  rejected_count: number
}

/** Inspect a project panel workbook without changing persisted panels. */
export async function previewPanelImport(project: string, file: File) {
  const response = await axios.post<PanelImportPreview>(
    organizationPath(project, 'panels', 'imports', 'preview'),
    panelImportForm(file)
  )
  return response.data
}

/** Apply the exact project panel workbook accepted in preview. */
export async function confirmPanelImport(project: string, file: File, confirmationToken: string) {
  const response = await axios.post<PanelImportResult>(
    organizationPath(project, 'panels', 'imports', 'confirm'),
    panelImportForm(file, confirmationToken)
  )
  return response.data
}

function panelImportForm(file: File, confirmationToken?: string) {
  const data = new FormData()
  data.append('file', file)
  if (confirmationToken) data.append('confirmation_token', confirmationToken)
  return data
}
