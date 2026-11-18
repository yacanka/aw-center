const QUICK_FILTERS: Record<string, Record<string, string>> = {
  archived: { archived: 'true' }
}

export const DASHBOARD_FILTER_KEYS = [
  'dashboard_delivery',
  'dashboard_cat',
  'dashboard_panel',
  'dashboard_panel_id'
] as const

/** Read the dashboard selection and its optional scope from a document table URL. */
export function compdocDashboardFilters(query: Record<string, unknown>): Record<string, string> {
  const filters: Record<string, string> = {}
  const [delivery, cat, panel, panelId] = DASHBOARD_FILTER_KEYS.map((key) => query[key])
  if (
    typeof delivery === 'string' &&
    (/^(delayed|expected|missing_target)$/.test(delivery) ||
      /^issued:[\s\S]{1,128}$/u.test(delivery))
  )
    filters.dashboard_delivery = delivery
  if (typeof cat === 'string' && Array.from(cat).length <= 12) filters.dashboard_cat = cat
  if (!Object.keys(filters).length) return filters
  if (typeof panel === 'string' && panel.length && Array.from(panel).length <= 255)
    filters.dashboard_panel = panel
  if (typeof panelId === 'string' && /^(unassigned|[1-9][0-9]{0,18})$/.test(panelId))
    filters.dashboard_panel_id = panelId
  return filters
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
