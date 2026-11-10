import type { WatcherDetailField } from '../api/watcher'

const defaultFieldIds = ['customfield_45000', 'customfield_45001', 'customfield_45002']

export function watcherComponentKey(name: string | null): string {
  return name === null ? 'none' : `component:${name}`
}

/** Keep per-project selections in order; an explicitly empty selection hides all fields. */
export function selectWatcherDetailFields(
  fields: WatcherDetailField[],
  projectSlugs: string[],
  selections: Record<string, string[]>,
  components?: string[],
  componentSelections: Record<string, string[]> = {}
): WatcherDetailField[] {
  const legacy = projectSlugs.length
    ? projectSlugs.flatMap((slug) => selections[slug] ?? defaultFieldIds)
    : defaultFieldIds
  const ids = new Set(
    components === undefined
      ? legacy
      : (components.length ? components : [null]).flatMap(
          (name) => componentSelections[watcherComponentKey(name)] ?? legacy
        )
  )
  const available = new Map(fields.map((field) => [field.id, field]))
  return [...ids].flatMap((id) => {
    const field = available.get(id)
    return field ? [field] : []
  })
}
