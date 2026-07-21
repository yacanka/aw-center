export interface PaginationQuery {
  page?: number
  page_size?: number
  [key: string]: string | number | boolean | Array<string | number> | null | undefined
}

export interface PaginationMeta {
  count: number
  next: string | null
  previous: string | null
}

export interface PaginatedResponse<T> extends PaginationMeta {
  results: T[]
}

/** Returns true when a payload follows the DRF pagination contract. */
export function isPaginatedResponse<T>(payload: unknown): payload is PaginatedResponse<T> {
  if (!payload || typeof payload !== 'object') return false

  const candidate = payload as Partial<PaginatedResponse<T>>
  return (
    typeof candidate.count === 'number' &&
    'next' in candidate &&
    'previous' in candidate &&
    Array.isArray(candidate.results)
  )
}

/** Extracts result arrays from paginated or legacy list responses. */
export function getPaginatedResults<T>(payload: unknown): T[] {
  if (isPaginatedResponse<T>(payload)) return payload.results
  if (Array.isArray(payload)) return payload as T[]

  return []
}

/** Extracts pagination metadata from DRF responses for remote tables. */
export function getPaginationMeta<T>(payload: unknown): PaginationMeta | null {
  if (!isPaginatedResponse<T>(payload)) return null

  return {
    count: payload.count,
    next: payload.next,
    previous: payload.previous
  }
}

/** Removes empty filters before sending query parameters to the API. */
export function compactPaginationQuery(query: PaginationQuery): PaginationQuery {
  return Object.fromEntries(
    Object.entries(query).filter(
      ([, value]) =>
        value !== null &&
        value !== undefined &&
        value !== '' &&
        (!Array.isArray(value) || value.length)
    )
  )
}
