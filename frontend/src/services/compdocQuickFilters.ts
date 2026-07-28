const QUICK_FILTERS: Record<string, Record<string, string>> = {
  mine: { mine: 'true' },
  my_team: { my_team: 'true' },
  unassigned: { unassigned: 'true' },
  due_soon: { due: 'soon' },
  overdue: { due: 'overdue' },
  review: { review: 'review' },
  approval: { review: 'approval' },
  archived: { archived: 'true' }
}

/** Convert bounded route query values into initial CompDoc table filters. */
export function compdocRouteFilters(query: Record<string, unknown>): Record<string, string> {
  const filters: Record<string, string> = {}
  const document = boundedQueryValue(query.document, 36)
  if (document) filters.id = document
  const name = boundedQueryValue(query.name, 256)
  if (name) filters.name = name
  for (const key of ['mine', 'my_team', 'unassigned', 'due', 'review', 'archived']) {
    const value = boundedQueryValue(query[key], 32)
    if (value) filters[key] = value
  }
  return filters
}

/** Return the server query represented by one toolbar quick-filter value. */
export function compdocQuickFilter(value: string): Record<string, string> {
  return QUICK_FILTERS[value] || {}
}

function boundedQueryValue(value: unknown, limit: number): string {
  return typeof value === 'string' ? value.trim().slice(0, limit) : ''
}
