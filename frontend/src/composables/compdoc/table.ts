import { ICompDoc } from '@/models/compdocs'

export type CompdocFilterValue = Record<string, unknown>

export interface CompdocPaginationState {
  page: number
  pageSize: number
}

export interface IssueCheckResult {
  success: boolean
}

/** Build the backend query for the remote compliance document table. */
export function buildCompdocTableQuery(
  filters: CompdocFilterValue,
  pagination: CompdocPaginationState
) {
  return {
    ...filters,
    page: pagination.page,
    page_size: pagination.pageSize
  }
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
