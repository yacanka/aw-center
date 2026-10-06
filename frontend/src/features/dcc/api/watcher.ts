import { apiClient } from '@/shared/api/http'
import type { IDcc } from '../models/dcc'

export interface WatcherIssueStatus {
  issue: string
  title: string
  status: string
  completed: boolean
  jira_issue_url: string
}
export interface WatcherStatus extends WatcherIssueStatus {
  subtasks: WatcherIssueStatus[]
  ecd_number: string
  ecd_revision: string
  dcc_number: string
  checked_at: string
}
export interface WatcherAssessment {
  document: Record<string, string>
  assessment: string
}
export async function importWatcherIssue(issue: string): Promise<IDcc> {
  return (await apiClient.post<IDcc>('dcc/records/import/', { issue })).data
}
export async function fetchWatcherStatus(id: string): Promise<WatcherStatus> {
  return (await apiClient.post<WatcherStatus>(`dcc/records/${id}/status/`, {})).data
}
export async function updateWatcherRecord(
  record: IDcc,
  title: string,
  active: boolean
): Promise<IDcc> {
  return (
    await apiClient.patch<IDcc>(`dcc/records/${record.id}/`, {
      title,
      active,
      version: record.version
    })
  ).data
}
export async function deleteWatcherRecord(record: IDcc): Promise<void> {
  await apiClient.delete(`dcc/records/${record.id}/`, { data: { version: record.version } })
}
export async function assessWatcherPdf(
  file: File,
  projectSlugs: string[]
): Promise<WatcherAssessment> {
  const data = new FormData()
  data.append('file', file)
  projectSlugs.forEach((slug) => data.append('project_slugs', slug))
  // Allow the adapter's 60s connect + 300s read budget and bounded PDF parsing.
  return (await apiClient.post<WatcherAssessment>('dcc/assessments/', data, { timeout: 390_000 }))
    .data
}
