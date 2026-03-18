export const STORAGE_KEYS = {
  token: "token",
  user: "user",
  project: "project",
} as const

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
