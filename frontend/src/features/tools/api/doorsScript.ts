import { apiClient } from '@/shared/api/http'
import { API_PATHS } from '@/shared/api/apiPaths'

export interface DoorsScriptResult {
  script: string
  row_count: number
  mapping_count: number
}

/** Read validated workbook columns for the route-local mapping form. */
export async function getExcelColumns(workbook: FormData): Promise<string[]> {
  const response = await apiClient.post<string[]>(`${API_PATHS.excel}/get_excel_columns/`, workbook)
  return response.data
}

/** Create one bounded DXL script from the submitted route-local workbook form. */
export async function createDoorsScript(workbook: FormData): Promise<DoorsScriptResult> {
  const response = await apiClient.post<DoorsScriptResult>(`${API_PATHS.doors}/script/`, workbook)
  return response.data
}
