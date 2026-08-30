import { apiClient as axios } from '@/shared/api/http'
import type { ICompDocActivity } from '@/features/compliance/models/compdocs'
import { compdocDocumentPath } from '@/shared/api/apiPaths'

export interface TransitionRequest {
  version: number
  status: string
  effective_date: string
  next_action_due_date?: string | null
  reason: string
}

interface ActivityResponse {
  results: unknown[]
}

interface TransitionResponse {
  document_id: string
  version: number
  event_id: string
}

export interface CompdocWork {
  owner: number | null
  owner_username: string
  owner_group: number | null
  owner_group_name: string
  next_action_due_date: string | null
  version: number
}

export interface CompdocReview {
  id: string
  kind: 'review' | 'approval'
  status: 'pending' | 'approved' | 'changes_requested' | 'cancelled' | 'superseded'
  assignee: number | null
  assignee_username: string
  due_date: string | null
  request_note: string
  decision_note: string
  requested_by_username: string
  decided_by_username: string
  source_version: number
  created_at: string
  allowed_actions: {
    approve: boolean
    request_changes: boolean
    cancel: boolean
  }
}

/** Load the bounded unified audit timeline for one document. */
export async function fetchCompdocActivity(
  project: string,
  documentId: string
): Promise<ICompDocActivity[]> {
  const response = await axios.get<ActivityResponse>(
    `${compdocDocumentPath(project, documentId)}/activity/`
  )
  if (!Array.isArray(response.data.results)) {
    throw new Error('The compliance activity response is invalid.')
  }
  return response.data.results.map(normalizeActivity)
}

function normalizeActivity(value: unknown): ICompDocActivity {
  if (!isRecord(value) || typeof value.type !== 'string' || typeof value.at !== 'string') {
    throw new Error('The compliance activity response is invalid.')
  }
  const data = isRecord(value.data) ? value.data : {}
  if (value.type === 'workflow') {
    return {
      type: 'workflow',
      occurred_at: value.at,
      actor: stringValue(data.actor),
      reason: stringValue(data.reason),
      status: stringValue(data.status),
      previous_status: stringValue(data.previous_status)
    }
  }
  const type = data.kind === 'approval' ? 'approval' : 'review'
  return {
    type,
    occurred_at: value.at,
    actor: stringValue(data.decided_by_username || data.requested_by_username),
    reason: stringValue(data.decision_note || data.request_note),
    status: stringValue(data.status)
  }
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Object.prototype.toString.call(value) === '[object Object]'
}

/** Append an actor-attributed lifecycle transition. */
export async function transitionCompdoc(
  project: string,
  documentId: string,
  request: TransitionRequest
): Promise<TransitionResponse> {
  const response = await axios.post<TransitionResponse>(
    `${compdocDocumentPath(project, documentId)}/transitions/`,
    request
  )
  return response.data
}

/** Load document ownership and its optimistic version. */
export async function fetchCompdocWork(project: string, documentId: string): Promise<CompdocWork> {
  const response = await axios.get<CompdocWork>(`${compdocDocumentPath(project, documentId)}/work/`)
  return response.data
}

/** Save an explicit subset of work assignment fields. */
export async function updateCompdocWork(
  project: string,
  documentId: string,
  request: Partial<CompdocWork> & { version: number; reason: string }
): Promise<CompdocWork> {
  const response = await axios.put<CompdocWork>(
    `${compdocDocumentPath(project, documentId)}/work/`,
    request
  )
  return response.data
}

/** Load bounded review and approval tasks. */
export async function fetchCompdocReviews(
  project: string,
  documentId: string
): Promise<CompdocReview[]> {
  const response = await axios.get<{ results: CompdocReview[] }>(
    `${compdocDocumentPath(project, documentId)}/reviews/`
  )
  return response.data.results
}

/** Create a review or approval task against the viewed document version. */
export async function createCompdocReview(
  project: string,
  documentId: string,
  request: Record<string, unknown>
): Promise<CompdocReview> {
  const response = await axios.post<CompdocReview>(
    `${compdocDocumentPath(project, documentId)}/reviews/`,
    request
  )
  return response.data
}

/** Record an assigned user's signed review decision. */
export async function decideCompdocReview(
  project: string,
  documentId: string,
  reviewId: string,
  status: 'approved' | 'changes_requested' | 'cancelled',
  decisionNote: string
): Promise<CompdocReview> {
  const response = await axios.post<CompdocReview>(
    `${compdocDocumentPath(project, documentId)}/reviews/${encodeURIComponent(reviewId)}/decision/`,
    { status, decision_note: decisionNote }
  )
  return response.data
}
