const QUICK_COMMANDS_KEY = 'quick_commands'

/** Return the account-scoped storage key used by recent quick commands. */
export function quickCommandStorageKey(userId?: number): string {
  return `${QUICK_COMMANDS_KEY}:${userId || 'anonymous'}`
}

export function writeJson<T>(key: string, value: T) {
  localStorage.setItem(key, JSON.stringify(value))
}

export function readJson<T>(key: string, fallback: T): T {
  const raw = localStorage.getItem(key)
  if (!raw) {
    return fallback
  }

  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}
