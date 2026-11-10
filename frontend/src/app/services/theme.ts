import type { IPreferences } from '@/features/session/models/auth'

export type ThemeName = 'dark' | 'light'
const THEME_STORAGE_KEY = 'aw-center.theme'

/** Returns the operating system's current color scheme. */
export function getSystemTheme(): ThemeName {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** Account preferences take precedence over the last preference used in this browser. */
export function resolvePreferredTheme(preferences?: Partial<IPreferences>): ThemeName {
  let preference = preferences?.theme
  if (!preference) {
    try {
      const saved = window.localStorage.getItem(THEME_STORAGE_KEY)
      if (saved === 'light' || saved === 'dark' || saved === 'system') preference = saved
    } catch {
      // Browser storage may be disabled; system preference remains available.
    }
  }
  return preference === 'dark' || preference === 'light' ? preference : getSystemTheme()
}

/** Applies the theme and remembers only the non-sensitive color preference across sessions. */
export function applyPreferredTheme(preferences?: Partial<IPreferences>): ThemeName {
  const preference = preferences?.theme
  if (preference === 'light' || preference === 'dark' || preference === 'system') {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, preference)
    } catch {
      // A storage failure must not prevent applying the authenticated preference.
    }
  }
  const theme = resolvePreferredTheme(preferences)
  document.documentElement.setAttribute('data-theme', theme)
  return theme
}
