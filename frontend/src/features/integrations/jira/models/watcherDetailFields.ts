import type { WatcherDetailField } from '../api/watcher'

const defaultFieldIds = ['customfield_45000', 'customfield_45001', 'customfield_45002']

/** Keep per-project selections in order; an explicitly empty selection hides all fields. */
export function selectWatcherDetailFields(
  fields: WatcherDetailField[],
  projectSlugs: string[],
  selections: Record<string, string[]>
): WatcherDetailField[] {
  const ids = new Set(projectSlugs.flatMap((slug) => selections[slug] ?? defaultFieldIds))
  const available = new Map(fields.map((field) => [field.id, field]))
  return [...ids].flatMap((id) => {
    const field = available.get(id)
    return field ? [field] : []
  })
}
