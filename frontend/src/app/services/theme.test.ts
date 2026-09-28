// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { applyPreferredTheme, resolvePreferredTheme } from './theme'

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: true }))
  )
})
afterEach(() => vi.restoreAllMocks())

it('keeps the selected light theme after logout and on a subsequent startup', async () => {
  applyPreferredTheme({ theme: 'light' })
  expect(applyPreferredTheme({})).toBe('light')
  expect(document.documentElement.dataset.theme).toBe('light')
  vi.resetModules()
  const fresh = await import('./theme')
  expect(fresh.resolvePreferredTheme()).toBe('light')
})

it('lets the account preference override the remembered browser preference', () => {
  applyPreferredTheme({ theme: 'light' })
  expect(applyPreferredTheme({ theme: 'dark' })).toBe('dark')
  expect(resolvePreferredTheme()).toBe('dark')
})

it('remembers system mode rather than freezing its resolved color', () => {
  applyPreferredTheme({ theme: 'light' })
  expect(applyPreferredTheme({ theme: 'system' })).toBe('dark')
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: false }))
  )
  expect(resolvePreferredTheme()).toBe('light')
})

it('ignores invalid stored preferences', () => {
  localStorage.setItem('aw-center.theme', 'invalid')
  expect(resolvePreferredTheme()).toBe('dark')
})

it('applies the account theme even when browser storage is unavailable', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('blocked')
  })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('blocked')
  })
  expect(applyPreferredTheme({ theme: 'light' })).toBe('light')
  expect(resolvePreferredTheme()).toBe('dark')
})
