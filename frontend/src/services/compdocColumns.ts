import type { IColumnSetting, ICompDocFieldMetadata } from '@/models/compdocs'

const STORAGE_PREFIX = 'compdocs>column_settings'
const MINIMUM_WIDTH = 60
const MAXIMUM_WIDTH = 600

interface StoredColumnSettings {
  schema_version: number
  project: string
  settings: unknown
}

/** Return schema-compatible saved settings for one project. */
export function readCompdocColumnSettings(
  project: string,
  fields: ICompDocFieldMetadata[]
): IColumnSetting[] {
  const raw = localStorage.getItem(storageKey(project))
  if (!raw) return createDefaultColumnSettings(fields)
  try {
    const stored = JSON.parse(raw) as StoredColumnSettings
    if (stored.project !== project) throw new Error('Project mismatch')
    return reconcileColumnSettings(stored.settings, fields)
  } catch {
    localStorage.removeItem(storageKey(project))
    return createDefaultColumnSettings(fields)
  }
}

/** Persist validated settings with their server schema identity. */
export function saveCompdocColumnSettings(
  project: string,
  schemaVersion: number,
  settings: IColumnSetting[]
) {
  localStorage.setItem(
    storageKey(project),
    JSON.stringify({ schema_version: schemaVersion, project, settings })
  )
}

/** Remove only the active project's table preferences. */
export function clearCompdocColumnSettings(project: string) {
  localStorage.removeItem(storageKey(project))
}

/** Create the server-recommended initial column layout. */
export function createDefaultColumnSettings(fields: ICompDocFieldMetadata[]) {
  return fields.filter((field) => field.default_visible).map(createSetting)
}

/** Create a layout containing every server field. */
export function createAllColumnSettings(fields: ICompDocFieldMetadata[]) {
  return fields.map(createSetting)
}

/** Drop stale/duplicate keys and apply current server capabilities. */
export function reconcileColumnSettings(settings: unknown, fields: ICompDocFieldMetadata[]) {
  const fieldsByKey = new Map(fields.map((field) => [field.key, field]))
  const seen = new Set<string>()
  const reconciled = validSettings(settings).flatMap((setting) => {
    const field = fieldsByKey.get(setting.key)
    if (!field || seen.has(setting.key)) return []
    seen.add(setting.key)
    return [sanitizeSetting(setting, field)]
  })
  fields
    .filter((field) => field.default_visible && !seen.has(field.key))
    .forEach((field) => {
      reconciled.push(createSetting(field))
    })
  return reconciled.length ? reconciled : createDefaultColumnSettings(fields)
}

function createSetting(field: ICompDocFieldMetadata): IColumnSetting {
  return {
    key: field.key,
    width: field.width,
    sorter: field.sortable,
    filter: field.filter_kind !== 'none',
    ellipsis: field.ellipsis
  }
}

function sanitizeSetting(setting: IColumnSetting, field: ICompDocFieldMetadata): IColumnSetting {
  const width = Number(setting.width)
  return {
    key: field.key,
    width: Math.min(
      MAXIMUM_WIDTH,
      Math.max(MINIMUM_WIDTH, Number.isFinite(width) ? width : field.width)
    ),
    sorter: Boolean(setting.sorter && field.sortable),
    filter: Boolean(setting.filter && field.filter_kind !== 'none'),
    ellipsis: Boolean(setting.ellipsis)
  }
}

function validSettings(value: unknown): IColumnSetting[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is IColumnSetting => {
    if (!item || typeof item !== 'object') return false
    return typeof (item as Partial<IColumnSetting>).key === 'string'
  })
}

function storageKey(project: string) {
  return `${STORAGE_PREFIX}>${project}`
}
