import axios from 'axios'
import type { Job } from '@/services/jobs'

export type TraceJobStatus =
  | 'awaiting_confirmation'
  | 'queued'
  | 'running'
  | 'cancel_requested'
  | 'cancelled'
  | 'succeeded'
  | 'failed'
  | 'archived'

export type TraceSourceComparisonStatus = 'changed' | 'unchanged' | 'unavailable'

export type TraceRefreshStatus =
  | 'current'
  | 'no_visible_change'
  | 'owner_required'
  | 'permission_required'
  | 'source_archived'
  | 'source_active'
  | 'ready'

export interface TraceChangedField {
  code: string
  label: string
  category: 'reference' | 'workflow' | 'identity' | 'classification' | 'ownership'
}

export interface TraceSourceChange {
  comparison_status: TraceSourceComparisonStatus
  captured_fields_changed: boolean
  changed_field_count: number
  changed_fields: TraceChangedField[]
}

export interface CompdocDccTrace {
  id: string
  issue_key: string
  source_history_id: number | null
  source_history_at: string | null
  source_fingerprint: string
  confirmed_at: string
  is_current_version: boolean
  source_change: TraceSourceChange
  job_status: TraceJobStatus
  job_attempt: number | null
  job_completed_at: string | null
  job_id: string | null
  can_open_job: boolean
  output_available: boolean
  can_refresh_preview: boolean
  refresh_status: TraceRefreshStatus
}

export interface CompdocDccTracePage {
  count: number
  next: string | null
  previous: string | null
  results: CompdocDccTrace[]
}

/** Fetch one permission-scoped page of reverse CompDoc-to-DCC provenance. */
export async function fetchCompdocDccTraces(
  project: string,
  compdocId: string,
  page: number,
  pageSize: number,
  signal?: AbortSignal
): Promise<CompdocDccTracePage> {
  const response = await axios.get<CompdocDccTracePage>('/dcc/compdoc-traceability/', {
    params: { project, compdoc_id: compdocId, page, page_size: pageSize },
    signal
  })
  return response.data
}

/** Create or replay a credential-free preview with the current linked CompDocs. */
export async function refreshCompdocDccTrace(traceId: string): Promise<Job> {
  const response = await axios.post<Job>(
    `/dcc/compdoc-traceability/${traceId}/refresh-preview/`,
    {},
    { headers: { 'Idempotency-Key': crypto.randomUUID() } }
  )
  return response.data
}
