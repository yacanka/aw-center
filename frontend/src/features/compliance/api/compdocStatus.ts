import type { ICompDoc } from '@/features/compliance/models/compdocs'

const DAY_MILLISECONDS = 86_400_000

/** Return a display-only delayed status without mutating API data. */
export function withCompdocDisplayStatus(row: ICompDoc, today = new Date()) {
  if (row.status !== 'to_be_issued' || !row.ubm_target_date) return row
  const targetDay = isoDay(row.ubm_target_date)
  if (targetDay === null) return row
  const currentDay = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  const overdueDays = Math.floor((currentDay - targetDay) / DAY_MILLISECONDS)
  return overdueDays > 0 ? { ...row, status: 'delayed' } : row
}

function isoDay(value: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim())
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const timestamp = Date.UTC(year, month - 1, day)
  const parsed = new Date(timestamp)
  return parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
    ? timestamp
    : null
}
