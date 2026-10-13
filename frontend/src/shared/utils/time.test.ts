import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  dateDaysOffset,
  formatTurkishDate,
  formatTurkishDateTime,
  formatTurkishTime,
  getTodayEUFormat,
  isoToTurkishDateTime
} from './time'

afterEach(() => vi.useRealTimers())

describe('Turkish date/time display', () => {
  it('displays UTC instants in Istanbul across the midnight boundary', () => {
    expect(isoToTurkishDateTime('2026-10-13T22:05:06Z')).toBe('14.10.2026 01:05:06')
  })

  it('uses the Istanbul calendar day for today', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-13T22:05:06Z'))
    expect(getTodayEUFormat()).toBe('14.10.2026')
  })
})

it('keeps calendar dates unchanged and rejects invalid calendar values', () => {
  expect(formatTurkishDate('2026-01-01')).toBe('01.01.2026')
  expect(formatTurkishDate('29.02.2024')).toBe('29.02.2024')
  expect(formatTurkishDate('2026-02-30')).toBe('-')
  expect(formatTurkishDate(null)).toBe('-')
})

it('normalizes timezone offsets and uses Turkish 24-hour time', () => {
  expect(formatTurkishDateTime('2026-10-13T19:05:06-03:00')).toBe('14.10.2026 01:05')
  expect(formatTurkishTime('2026-10-13T22:05:06Z')).toBe('01:05:06')
  expect(formatTurkishDateTime('invalid')).toBe('-')
})

it('treats timezone-less Turkish timestamps consistently and shows midnight as 00', () => {
  expect(formatTurkishDateTime('2026-10-14T00:05:06', true)).toBe('14.10.2026 00:05:06')
  expect(formatTurkishTime('2026-10-13T21:00:00Z')).toBe('00:00:00')
  expect(formatTurkishDate('2026-10-13T22:05:06Z')).toBe('14.10.2026')
})

it('offsets the Istanbul calendar date without host timezone drift', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-13T22:05:06Z'))
  expect(dateDaysOffset(1)).toBe('15.10.2026')
  expect(dateDaysOffset(-1, '2026-01-01')).toBe('31.12.2025')
})
