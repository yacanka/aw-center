import type { ICompDoc } from '@/models/compdocs'

export type CompdocFilterValue = Record<string, unknown>

export interface CompdocPaginationState {
  page: number
  pageSize: number
}

export interface IssueCheckResult {
  success: boolean
}

const DATE_OPERATOR_LOOKUPS: Record<string, string> = {
  '==': '',
  '!=': '__not',
  '>': '__gt',
  '>=': '__gte',
  '<': '__lt',
  '<=': '__lte'
}

/** Build the backend query for the remote compliance document table. */
export function buildCompdocTableQuery(
  filters: CompdocFilterValue,
  pagination: CompdocPaginationState,
  ordering: string | null = null
) {
  return {
    ...serializeCompdocFilters(filters),
    page: pagination.page,
    page_size: pagination.pageSize,
    ordering
  }
}

/** Serialize UI filter state into the validated backend query contract. */
export function serializeCompdocFilters(filters: CompdocFilterValue) {
  return Object.fromEntries(
    Object.entries(filters).flatMap(([key, value]) => serializeFilter(key, value))
  )
}

/** Return unique non-empty tech document numbers from both tech-doc columns. */
export function collectUniqueTechDocumentNumbers(rows: ICompDoc[]) {
  return [...new Set(rows.flatMap(getTechDocumentNumbers).filter(Boolean))] as string[]
}

/** Wait for the requested retry delay. */
export function waitForRetry(delayMilliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, delayMilliseconds))
}

/** Run asynchronous work with a fixed concurrency limit while preserving order. */
export async function mapWithConcurrencyLimit<T, R>(
  items: T[],
  limit: number,
  task: (item: T) => Promise<R>
) {
  const results: R[] = []
  let nextIndex = 0

  async function worker() {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex++
      results[currentIndex] = await task(items[currentIndex])
    }
  }

  const workers = Array.from({ length: Math.min(limit, items.length) }, worker)
  await Promise.all(workers)
  return results
}

function getTechDocumentNumbers(row: ICompDoc) {
  return [row.tech_doc_no, row.tech_doc_no_2]
}

function serializeFilter(key: string, value: unknown): [string, string | boolean | unknown[]][] {
  if (value === null || value === undefined || value === '') return []
  if (Array.isArray(value)) return value.length ? [[key, value]] : []
  if (isDateFilter(value)) {
    const lookup = DATE_OPERATOR_LOOKUPS[value.type]
    const date = toIsoDate(value.date)
    return lookup === undefined || !date ? [] : [[`${key}${lookup}`, date]]
  }
  if (typeof value === 'string' || typeof value === 'boolean') return [[key, value]]
  return []
}

function isDateFilter(value: unknown): value is { date: string; type: string } {
  if (!value || typeof value !== 'object') return false
  const candidate = value as { date?: unknown; type?: unknown }
  return typeof candidate.date === 'string' && typeof candidate.type === 'string'
}

function toIsoDate(value: string) {
  const european = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value)
  if (european) return `${european[3]}-${european[2]}-${european[1]}`
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null
}
