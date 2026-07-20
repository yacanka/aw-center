import axios from 'axios'

export type AttentionSeverity = 'critical' | 'warning'
export type AttentionKind = 'job' | 'import' | 'invitation' | 'jira_draft' | 'compdoc_trace'
export type AttentionDecisionAction = 'snooze' | 'dismiss'

export interface AttentionItem {
  id: string
  kind: AttentionKind
  severity: AttentionSeverity
  title: string
  detail: string
  guidance: string
  action_label: string
  action_path: string
  occurred_at: string
  due_at?: string
}

export interface AttentionSummary {
  total: number
  critical: number
  warning: number
}

export interface ActionCenterResponse {
  generated_at: string
  summary: AttentionSummary
  items: AttentionItem[]
}

/** Return the current user's permission-aware cross-workflow attention queue. */
export async function fetchActionCenter(): Promise<ActionCenterResponse> {
  const response = await axios.get<ActionCenterResponse>('/action-center/')
  return response.data
}

/** Temporarily snooze or permanently dismiss one authorized attention item. */
export async function updateAttentionDecision(
  itemId: string,
  action: AttentionDecisionAction
): Promise<void> {
  await axios.post('/action-center/decisions/', { item_id: itemId, action })
}
