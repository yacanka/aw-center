import { apiClient } from '@/shared/api/http'
import type { Job } from '@/features/jobs/api/jobs'

export type ComparisonFamily = 'word' | 'excel' | 'pdf'
export interface ComparisonOptions {
  preset: string
  equal_ratio: number
  weak_equal_ratio: number
  output_type: 'word' | 'excel'
}
export interface ComparisonPreset {
  id: string
  label: string
  description: string
  equal_ratio: number
  weak_equal_ratio: number
}
export interface TableSelection {
  sheet: string
  header_row?: number
}
export interface ExcelSelection {
  first?: TableSelection
  second?: TableSelection
  columns?: [number, number][]
  matching?: { mode: 'auto' | 'keys' | 'position'; keys?: number[] }
}
export interface TableInspection {
  sheets: { name: string; headers: { row: number; labels: string[] }[] }[]
  selected: TableSelection
  columns: string[]
  preview: string[][]
  row_count: number
}
export interface ComparisonInspection {
  first: TableInspection
  second: TableInspection
  selection: ExcelSelection
  options: ComparisonOptions
  matching: {
    method: string
    requires_input: boolean
    reason: string
    keys: number[]
    ambiguous_count?: number
  }
  warnings: string[]
}
export type ComparisonInput = { files: [File, File] } | { inspectionId: string }

export function comparisonFamily(name: string): ComparisonFamily | null {
  const extension = name.split('.').at(-1)?.toLowerCase()
  if (extension === 'docx' || extension === 'docm') return 'word'
  if (extension === 'xlsx' || extension === 'xlsm') return 'excel'
  return extension === 'pdf' ? 'pdf' : null
}

export async function fetchComparisonPresets(): Promise<{
  presets: ComparisonPreset[]
  default: string
}> {
  return (await apiClient.get('tools/compare/presets/')).data
}

/** Inspect an owner-bound private artifact, without exposing its storage path. */
export async function fetchInspection(id: string): Promise<ComparisonInspection> {
  return (await apiClient.get(`tools/compare/inspections/${id}/`)).data
}

/** A caller retains its idempotency key across uncertain retries of the same request. */
export async function enqueueComparison(
  inspection: boolean,
  input: ComparisonInput,
  options: ComparisonOptions,
  idempotencyKey: string,
  selection?: ExcelSelection
): Promise<Job> {
  const body = new FormData()
  if ('files' in input) {
    body.append('first', input.files[0])
    body.append('second', input.files[1])
  } else body.append('inspection_id', input.inspectionId)
  body.append('parameters', JSON.stringify({ ...options, ...(selection ? { selection } : {}) }))
  return (
    await apiClient.post<Job>(`tools/compare/${inspection ? 'inspections' : 'jobs'}/`, body, {
      headers: { 'Idempotency-Key': idempotencyKey }
    })
  ).data
}
