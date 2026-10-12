import { apiClient } from '@/shared/api/http'
import type { Job } from '@/features/jobs/api/jobs'
import type { IJiraField, JiraFieldValue } from '@/features/integrations/jira/models/jira'

export interface JiraSubtaskItem {
  summary: string
  description?: string
  assignee?: string
  due_date?: string | null
  fields: Record<string, JiraFieldValue>
}

export interface WorkbookMapping {
  column: string
  field: string
}

export async function fetchSubtaskFields(
  issue: string,
  includeSummary = false
): Promise<{ issue: string; fields: IJiraField[] }> {
  return (
    await apiClient.post('integrations/jira/subtasks/fields/', {
      issue,
      ...(includeSummary ? { include_summary: true } : {})
    })
  ).data
}

export async function inspectSubtaskWorkbook(file: File): Promise<string[]> {
  const form = new FormData()
  form.append('file', file)
  return (await apiClient.post<{ columns: string[] }>('integrations/jira/subtasks/workbook/', form))
    .data.columns
}

export async function createManualSubtaskJob(
  issue: string,
  items: JiraSubtaskItem[]
): Promise<Job> {
  return (
    await apiClient.post<Job>(
      'integrations/jira/subtasks/jobs/',
      { issue, items },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } }
    )
  ).data
}

export async function createWorkbookSubtaskJob(
  issue: string,
  file: File,
  mapping: WorkbookMapping[]
): Promise<Job> {
  const form = new FormData()
  form.append('issue', issue)
  form.append('file', file)
  form.append('mapping', JSON.stringify(mapping))
  return (
    await apiClient.post<Job>('integrations/jira/subtasks/jobs/', form, {
      headers: { 'Idempotency-Key': crypto.randomUUID() }
    })
  ).data
}

export async function resumeSubtaskJob(jobId: string): Promise<Job> {
  return (
    await apiClient.post<Job>(
      `integrations/jira/subtasks/jobs/${jobId}/resume/`,
      {},
      { headers: { 'Idempotency-Key': crypto.randomUUID() } }
    )
  ).data
}
