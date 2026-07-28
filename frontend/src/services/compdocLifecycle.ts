import axios from 'axios'
import type { ICompDocActivity } from '@/models/compdocs'

export interface TransitionRequest {
  source_history_id: number
  status: string
  effective_date: string
  next_action_due_date?: string | null
  reason: string
}

interface ActivityResponse {
  results: ICompDocActivity[]
}

interface TransitionResponse {
  document_id: string
  source_history_id: number
  event_id: string
}

export interface CompdocWork {
  owner: number | null
  owner_username: string
  owner_group: number | null
  owner_group_name: string
  next_action_due_date: string | null
  source_history_id: number
}

export interface CompdocAssignees {
  users: Array<{ id: number; username: string }>
  groups: Array<{ id: number; name: string }>
}

export interface CompdocReview {
  id: string
  kind: 'review' | 'approval'
  status: 'pending' | 'approved' | 'changes_requested' | 'cancelled'
  assignee: number | null
  assignee_username: string
  due_date: string | null
  request_note: string
  decision_note: string
  requested_by: string
  decided_by: string
  created_at: string
}

function documentPath(project: string, documentId: string): string {
  return `/${encodeURIComponent(project)}/compdocs/${encodeURIComponent(documentId)}`
}

/** Load the bounded unified audit timeline for one document. */
export async function fetchCompdocActivity(
  project: string,
  documentId: string
): Promise<ICompDocActivity[]> {
  const response = await axios.get<ActivityResponse>(
    `${documentPath(project, documentId)}/activity/`
  )
  return response.data.results
}

/** Append an actor-attributed lifecycle transition. */
export async function transitionCompdoc(
  project: string,
  documentId: string,
  request: TransitionRequest
): Promise<TransitionResponse> {
  const response = await axios.post<TransitionResponse>(
    `${documentPath(project, documentId)}/transitions/`,
    request
  )
  return response.data
}

/** Load document ownership and its optimistic version. */
export async function fetchCompdocWork(project: string, documentId: string): Promise<CompdocWork> {
  const response = await axios.get<CompdocWork>(`${documentPath(project, documentId)}/work/`)
  return response.data
}

/** Save an explicit subset of work assignment fields. */
export async function updateCompdocWork(
  project: string,
  documentId: string,
  request: Partial<CompdocWork> & { source_history_id: number; reason: string }
): Promise<CompdocWork> {
  const response = await axios.put<CompdocWork>(
    `${documentPath(project, documentId)}/work/`,
    request
  )
  return response.data
}

/** Search only project-visible active users and groups. */
export async function fetchCompdocAssignees(
  project: string,
  search = ''
): Promise<CompdocAssignees> {
  const response = await axios.get<CompdocAssignees>(
    `/${encodeURIComponent(project)}/compdocs/assignees/`,
    { params: { search } }
  )
  return response.data
}

/** Load bounded review and approval tasks. */
export async function fetchCompdocReviews(
  project: string,
  documentId: string
): Promise<CompdocReview[]> {
  const response = await axios.get<{ results: CompdocReview[] }>(
    `${documentPath(project, documentId)}/reviews/`
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
    `${documentPath(project, documentId)}/reviews/`,
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
    `${documentPath(project, documentId)}/reviews/${encodeURIComponent(reviewId)}/decision/`,
    { status, decision_note: decisionNote }
  )
  return response.data
}

/** Apply one homogeneous operation to at most 100 explicitly versioned documents. */
export async function bulkUpdateCompdocs(
  project: string,
  documents: Array<{ id: string; source_history_id: number }>,
  action: 'work' | 'transition' | 'archive' | 'restore',
  reason: string,
  values: Record<string, unknown> = {}
): Promise<void> {
  await axios.post(`/${encodeURIComponent(project)}/compdocs/bulk/`, {
    documents,
    action,
    reason,
    values
  })
}

/** Export at most 100 explicitly selected current documents. */
export async function exportSelectedCompdocs(
  project: string,
  documents: Array<{ id: string; source_history_id: number }>
): Promise<Blob> {
  const response = await axios.post(
    `/${encodeURIComponent(project)}/compdocs/excel/`,
    {
      documents
    },
    { responseType: 'blob' }
  )
  return response.data
}
