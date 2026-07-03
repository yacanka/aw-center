import type { IPreferences } from '@/models/auth'

export type ThemeName = 'dark' | 'light'

/**
 * Returns the browser-level theme preference for unauthenticated users.
 */
export function getSystemTheme(): ThemeName {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/**
 * Resolves the effective theme from user preferences, falling back to the system theme.
 */
export function resolvePreferredTheme(preferences?: Partial<IPreferences>): ThemeName {
  return preferences?.theme === 'dark' || preferences?.theme === 'light'
    ? preferences.theme
    : getSystemTheme()
}

/**
 * Applies the effective theme to the document root for global CSS variables.
 */
export function applyPreferredTheme(preferences?: Partial<IPreferences>): ThemeName {
  const theme = resolvePreferredTheme(preferences)
  document.documentElement.setAttribute('data-theme', theme)
  return theme
}
