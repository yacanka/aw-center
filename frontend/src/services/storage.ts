export const STORAGE_KEYS = {
  token: 'token',
  user: 'user',
  project: 'project',
  quickCommands: 'quick_commands',
  jiraSession: 'jira_session_id',
  jiraActiveTab: 'jira_active_tab'
} as const

/** Return the account-scoped storage key used by recent quick commands. */
export function quickCommandStorageKey(userId?: number): string {
  return `${STORAGE_KEYS.quickCommands}:${userId || 'anonymous'}`
}

export function writeString(key: string, value: string) {
  localStorage.setItem(key, value)
}

export function readString(key: string): string | null {
  return localStorage.getItem(key)
}

export function removeKey(key: string) {
  localStorage.removeItem(key)
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
