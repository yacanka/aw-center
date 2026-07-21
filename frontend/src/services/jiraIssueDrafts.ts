import axios from 'axios'
import type { IJiraField, JiraFieldValue } from '@/models/jira'

export type JiraIssueDraftStatus = 'draft' | 'approved' | 'publishing' | 'published' | 'failed'

export interface JiraIssueDraftEvent {
  id: number
  event_type: string
  version: number
  details: Record<string, unknown>
  created_at: string
}

export interface JiraIssueDraft {
  id: string
  source_job: string
  project_key: string
  summary: string
  description: string
  extra_fields: Record<string, JiraFieldValue>
  status: JiraIssueDraftStatus
  version: number
  jira_issue_key: string
  jira_issue_url: string | null
  approved_at: string | null
  published_at: string | null
  last_error_code: string
  last_error_message: string
  created_at: string
  updated_at: string
  events: JiraIssueDraftEvent[]
}

export interface JiraIssueDraftEdit {
  project_key: string
  summary: string
  description: string
  extra_fields: Record<string, JiraFieldValue>
  version: number
}

export interface JiraPreflightIdentity {
  id: string
  name: string
}

export interface JiraIssueDraftPreflight {
  ready: boolean
  project_key: string
  issue_type: string
  fields: IJiraField[]
  missing_fields: JiraPreflightIdentity[]
  invalid_fields: JiraPreflightIdentity[]
  unsupported_fields: JiraPreflightIdentity[]
  warnings: string[]
}

/** Create or replay the single owned JIRA draft for an analysis job. */
export async function createJiraIssueDraft(sourceJobId: string): Promise<JiraIssueDraft> {
  const response = await axios.post<JiraIssueDraft>('/dcc/issue-drafts/', {
    source_job_id: sourceJobId
  })
  return response.data
}

/** Refresh one owner-scoped JIRA issue draft. */
export async function fetchJiraIssueDraft(draftId: string): Promise<JiraIssueDraft> {
  const response = await axios.get<JiraIssueDraft>(`/dcc/issue-drafts/${draftId}/`)
  return response.data
}

/** Save a complete version-checked draft edit. */
export async function updateJiraIssueDraft(
  draftId: string,
  values: JiraIssueDraftEdit
): Promise<JiraIssueDraft> {
  const response = await axios.patch<JiraIssueDraft>(`/dcc/issue-drafts/${draftId}/`, values)
  return response.data
}

/** Record explicit human approval for the current draft version. */
export async function approveJiraIssueDraft(draft: JiraIssueDraft): Promise<JiraIssueDraft> {
  const response = await axios.post<JiraIssueDraft>(`/dcc/issue-drafts/${draft.id}/approve/`, {
    version: draft.version
  })
  return response.data
}

/** Inspect live JIRA create requirements without performing an external write. */
export async function preflightJiraIssueDraft(
  draft: JiraIssueDraft,
  sessionId: string
): Promise<JiraIssueDraftPreflight> {
  const response = await axios.post<JiraIssueDraftPreflight>(
    `/dcc/issue-drafts/${draft.id}/preflight/`,
    { JSESSIONID: sessionId }
  )
  return response.data
}

/** Publish an approved draft while keeping the JIRA session out of the durable draft payload. */
export async function publishJiraIssueDraft(
  draft: JiraIssueDraft,
  sessionId: string
): Promise<JiraIssueDraft> {
  const response = await axios.post<JiraIssueDraft>(`/dcc/issue-drafts/${draft.id}/publish/`, {
    version: draft.version,
    JSESSIONID: sessionId
  })
  return response.data
}
