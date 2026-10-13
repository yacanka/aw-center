import type { ICompDoc } from '@/features/compliance/models/compdocs'

const DAY_MILLISECONDS = 86_400_000

/** Derive unissued display labels without mutating API data or stored workflow codes. */
export function withCompdocDisplayStatus(row: ICompDoc, today = new Date()) {
  const target = row.ubm_revised_target_date || row.ubm_target_date
  if (
    row.status === 'airworthiness_review' &&
    (!row.status_label || row.status_label.toLowerCase() === 'airworthiness review')
  )
    return { ...row, status_label: 'Aw Review' }
  if (row.status !== 'to_be_issued') return row
  const defaultLabel =
    !row.status_label ||
    ['to be issued', 'in design', 'in design (date missing)'].includes(
      row.status_label.toLowerCase()
    )
  if (!target) return defaultLabel ? { ...row, status_label: 'In Design (date missing)' } : row
  const inDesign = defaultLabel ? { ...row, status_label: 'In Design' } : row
  if (row.ubm_delivery_date) return inDesign
  const targetDay = isoDay(target)
  if (targetDay === null) return inDesign
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Istanbul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(today)
  const part = (type: string) => Number(parts.find((item) => item.type === type)?.value)
  const currentDay = Date.UTC(part('year'), part('month') - 1, part('day'))
  const overdueDays = Math.floor((currentDay - targetDay) / DAY_MILLISECONDS)
  return overdueDays > 0 ? { ...row, status: 'delayed', status_label: 'Delayed' } : inDesign
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
