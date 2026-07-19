/** Parse a boolean feature flag without treating the string `false` as enabled. */
export function parseBooleanFeatureFlag(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value !== 'string') return fallback
  const normalized = value.trim().toLowerCase()
  if (['1', 'true', 'yes', 'on'].includes(normalized)) return true
  if (['0', 'false', 'no', 'off', ''].includes(normalized)) return false
  return fallback
}

export const SHOW_DELAYED_COMPDOCS = parseBooleanFeatureFlag(
  import.meta.env?.VITE_SHOW_DELAYED_COMPDOCS
)
