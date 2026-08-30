const QUICK_FILTERS: Record<string, Record<string, string>> = {
  archived: { archived: 'true' }
}

/** Convert bounded route query values into initial CompDoc table filters. */
export function compdocRouteFilters(query: Record<string, unknown>): Record<string, string> {
  const filters: Record<string, string> = {}
  const archived = boundedQueryValue(query.archived, 5)
  if (archived === 'true' || archived === 'all') filters.archived = archived
  return filters
}

/** Return the server query represented by one toolbar quick-filter value. */
export function compdocQuickFilter(value: string): Record<string, string> {
  return QUICK_FILTERS[value] || {}
}

function boundedQueryValue(value: unknown, limit: number): string {
  return typeof value === 'string' ? value.trim().slice(0, limit) : ''
}
