import { apiClient } from '@/shared/api/http'
import type { IJiraTrackedIssue } from '@/features/integrations/jira/models/records'
import {
  compactPaginationQuery,
  getPaginationMeta,
  type PaginatedResponse,
  type PaginationMeta,
  type PaginationQuery
} from '@/shared/services/pagination'

export interface JiraTrackedIssuePage {
  results: IJiraTrackedIssue[]
  pagination: PaginationMeta
}

export interface JiraReminderDelivery {
  id: string
  status: 'pending' | 'claimed' | 'sent' | 'failed'
  recipient_count: number
  error_code: string
  created_at: string
  sent_at: string | null
}

/** Load one server-authorized DCC page without retaining route state globally. */
export async function fetchJiraTrackedIssues(
  query: PaginationQuery = {}
): Promise<JiraTrackedIssuePage> {
  const response = await apiClient.get<PaginatedResponse<IJiraTrackedIssue>>(
    'integrations/jira/records/',
    {
      params: compactPaginationQuery(query)
    }
  )
  return {
    results: response.data.results,
    pagination: getPaginationMeta<IJiraTrackedIssue>(response.data) || {
      count: 0,
      next: null,
      previous: null
    }
  }
}

/** Queue a durable reminder without sending JIRA or SMTP credentials from the browser. */
export async function createDccReminder(
  record: IJiraTrackedIssue,
  ccbNo: number,
  dueDate: string
): Promise<JiraReminderDelivery> {
  return (
    await apiClient.post<JiraReminderDelivery>(
      `integrations/jira/records/${record.id}/reminders/`,
      { version: record.version, ccb_no: ccbNo, due_date: dueDate },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } }
    )
  ).data
}
