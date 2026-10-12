import { apiClient } from '@/shared/api/http'
import type { IJiraTrackedIssue } from '../models/records'

export interface WatcherIssueStatus {
  issue: string
  title: string
  status: string
  completed: boolean
  jira_issue_url: string
}
export interface WatcherDetailField {
  id: string
  label: string
  value: string
}
export interface WatcherPreferences {
  outstanding_only: boolean
  detail_fields: Record<string, string[]>
}
export interface WatcherPreferencesPatch {
  outstanding_only?: boolean
  project_slug?: string
  detail_field_ids?: string[]
}
export interface WatcherStatus extends WatcherIssueStatus {
  issue_completed: boolean
  record_version: number
  project_slugs: string[]
  detail_fields: WatcherDetailField[]
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
export async function importWatcherIssue(issue: string): Promise<IJiraTrackedIssue> {
  return (await apiClient.post<IJiraTrackedIssue>('integrations/jira/records/import/', { issue }))
    .data
}
export async function fetchWatcherStatus(id: string): Promise<WatcherStatus> {
  return (await apiClient.post<WatcherStatus>(`integrations/jira/records/${id}/status/`, {})).data
}
/** Read display preferences for the authenticated user. */
export async function fetchWatcherPreferences(): Promise<WatcherPreferences> {
  return (await apiClient.get<WatcherPreferences>('integrations/jira/watcher/preferences/')).data
}
/** Patch one Watcher preference without replacing other user settings. */
export async function updateWatcherPreferences(
  patch: WatcherPreferencesPatch
): Promise<WatcherPreferences> {
  return (
    await apiClient.patch<WatcherPreferences>('integrations/jira/watcher/preferences/', patch)
  ).data
}
export async function deleteWatcherRecord(record: IJiraTrackedIssue): Promise<void> {
  await apiClient.delete(`integrations/jira/records/${record.id}/`, {
    data: { version: record.version }
  })
}
export async function assessWatcherPdf(
  file: File,
  projectSlugs: string[]
): Promise<WatcherAssessment> {
  const data = new FormData()
  data.append('file', file)
  projectSlugs.forEach((slug) => data.append('project_slugs', slug))
  // Allow the adapter's 60s connect + 300s read budget and bounded PDF parsing.
  return (
    await apiClient.post<WatcherAssessment>('integrations/jira/assessments/', data, {
      timeout: 390_000
    })
  ).data
}
