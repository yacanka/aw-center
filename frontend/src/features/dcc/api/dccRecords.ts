import { apiClient } from '@/shared/api/http'
import type { IDcc } from '@/features/dcc/models/dcc'
import {
  compactPaginationQuery,
  getPaginationMeta,
  type PaginatedResponse,
  type PaginationMeta,
  type PaginationQuery
} from '@/shared/services/pagination'

export interface DccRecordPage {
  results: IDcc[]
  pagination: PaginationMeta
}

export interface DccReminderDelivery {
  id: string
  status: 'pending' | 'claimed' | 'sent' | 'failed'
  recipient_count: number
  error_code: string
  created_at: string
  sent_at: string | null
}

/** Load one server-authorized DCC page without retaining route state globally. */
export async function fetchDccRecords(query: PaginationQuery = {}): Promise<DccRecordPage> {
  const response = await apiClient.get<PaginatedResponse<IDcc>>('dcc/records/', {
    params: compactPaginationQuery(query)
  })
  return {
    results: response.data.results,
    pagination: getPaginationMeta<IDcc>(response) || { count: 0, next: null, previous: null }
  }
}

/** Queue a durable reminder without sending JIRA or SMTP credentials from the browser. */
export async function createDccReminder(
  record: IDcc,
  ccbNo: number,
  dueDate: string
): Promise<DccReminderDelivery> {
  return (
    await apiClient.post<DccReminderDelivery>(
      `dcc/records/${record.id}/reminders/`,
      { version: record.version, ccb_no: ccbNo, due_date: dueDate },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } }
    )
  ).data
}
