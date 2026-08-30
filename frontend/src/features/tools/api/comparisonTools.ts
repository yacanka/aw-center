import { apiClient } from '@/shared/api/http'

export type WordComparisonParameters = {
  equal_ratio: number
  weak_equal_ratio: number
  output_type: string | null
}

/** Compare two spreadsheets and return the generated workbook. */
export function compareExcelFiles(first: File, second: File, keyColumns: string[]): Promise<Blob> {
  return compareFiles('tools/excel/compare/', first, second, { keyColumns })
}

/** Compare two PDF documents and return the generated report. */
export function comparePdfFiles(first: File, second: File): Promise<Blob> {
  return compareFiles('tools/pdf/compare/', first, second)
}

/** Compare two Word documents and return the selected report format. */
export function compareWordFiles(
  first: File,
  second: File,
  parameters: WordComparisonParameters
): Promise<Blob> {
  return compareFiles('tools/word/compare/', first, second, parameters)
}

async function compareFiles(
  path: string,
  first: File,
  second: File,
  parameters?: object
): Promise<Blob> {
  const payload = new FormData()
  payload.append('first', first)
  payload.append('second', second)
  if (parameters) payload.append('json', JSON.stringify(parameters))
  return (await apiClient.post<Blob>(path, payload, { responseType: 'blob' })).data
}
