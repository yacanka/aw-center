import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { getDaysDifference, getTodayEUFormat } from '@/shared/utils/time'

/** Return a display-only delayed status without mutating API data. */
export function withCompdocDisplayStatus(row: ICompDoc) {
  if (row.status !== 'to_be_issued' || !row.ubm_target_date) return row
  const overdueDays = getDaysDifference(getTodayEUFormat(), row.ubm_target_date) || 0
  return overdueDays > 0 ? { ...row, status: 'delayed' } : row
}
