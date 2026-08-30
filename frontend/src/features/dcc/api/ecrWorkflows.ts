import { apiClient as axios } from '@/shared/api/http'
import type { PaginatedResponse } from '@/shared/services/pagination'
import type { JiraIssueDraftPreflight } from '@/features/dcc/api/jiraIssueDrafts'
import type { JiraFieldValue } from '@/features/dcc/models/jira'

export type EcrWorkflowStatus =
  | 'review'
  | 'approved'
  | 'rejected'
  | 'publishing'
  | 'published'
  | 'failed'
  | 'cancelled'
  | 'reconciliation_required'

export interface EcrSnapshot {
  ecr_number: string
  title: string
  project: string
  change_class: string
  change_type: string
  effectivity: string
  track_type: string
  record_of_change: string
  requestor: string
  originator: string
  ata: string
  subata: string
  initiator: string
  justification: string
  proposed_solution: string
  nonimplementation_consequence: string
  impacted_groups: string
}

export interface EcrSubtask {
  summary: string
  description: string
  assignee: string
  priority: string
  due_date: string | null
}

export interface EcrApproval {
  project_key: string
  extra_fields: Record<string, JiraFieldValue>
  subtasks: EcrSubtask[]
  approved_at: string | null
  rejected_at: string | null
}

export interface EcrPublicationError {
  code: string
  detail: string
}

export interface EcrPublication {
  job_id: string | null
  job_status: string | null
  jira_issue_key: string
  attachment_confirmed: boolean
  subtasks_confirmed: number
  subtasks_total: number
  published_at: string | null
  last_error: EcrPublicationError | null
}

export interface EcrAllowedActions {
  approve: boolean
  reject: boolean
  publish: boolean
  resume: boolean
  cancel: boolean
}

export interface EcrWorkflowEvent {
  type: string
  version: number
  code: string
  created_at: string
}

export interface EcrWorkflow {
  id: string
  status: EcrWorkflowStatus
  version: number
  project_slugs: string[]
  snapshot: EcrSnapshot
  approval: EcrApproval
  publication: EcrPublication
  allowed_actions: EcrAllowedActions
  created_at: string
  updated_at: string
  events?: EcrWorkflowEvent[]
}

export interface EcrApprovalInput {
  project_key: string
  extra_fields?: Record<string, JiraFieldValue>
  subtasks?: EcrSubtask[]
}

/** List the authenticated user's newest ECR reviews. */
export async function fetchEcrWorkflows(
  page = 1,
  pageSize = 20
): Promise<PaginatedResponse<EcrWorkflow>> {
  const response = await axios.get<PaginatedResponse<EcrWorkflow>>('workflows/ecr/', {
    params: { page, page_size: pageSize }
  })
  return response.data
}

/** Fetch one owner-scoped ECR review and its bounded audit history. */
export async function fetchEcrWorkflow(workflowId: string): Promise<EcrWorkflow> {
  const response = await axios.get<EcrWorkflow>(`workflows/ecr/${workflowId}/`)
  return response.data
}

/** Parse a private PDF into an immutable, human-reviewable ECR workflow. */
export async function createEcrWorkflow(
  file: File,
  projectSlugs: string[],
  idempotencyKey: string
): Promise<EcrWorkflow> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('project_slugs', JSON.stringify(projectSlugs))
  const response = await axios.post<EcrWorkflow>('workflows/ecr/', formData, {
    headers: { 'Idempotency-Key': idempotencyKey }
  })
  return response.data
}

/** Approve a complete, version-checked publication plan. */
export async function approveEcrWorkflow(
  workflow: EcrWorkflow,
  approval: EcrApprovalInput
): Promise<EcrWorkflow> {
  const response = await axios.post<EcrWorkflow>(`workflows/ecr/${workflow.id}/approve/`, {
    version: workflow.version,
    project_key: approval.project_key,
    extra_fields: approval.extra_fields || {},
    subtasks: approval.subtasks || []
  })
  return response.data
}

/** Inspect live JIRA requirements for the exact ECR approval draft. */
export async function preflightEcrWorkflow(
  workflow: EcrWorkflow,
  approval: EcrApprovalInput
): Promise<JiraIssueDraftPreflight> {
  const response = await axios.post<JiraIssueDraftPreflight>(
    `workflows/ecr/${workflow.id}/preflight/`,
    {
      version: workflow.version,
      project_key: approval.project_key,
      extra_fields: approval.extra_fields || {},
      subtasks: approval.subtasks || []
    }
  )
  return response.data
}

/** Reject the current reviewed version without performing an external write. */
export async function rejectEcrWorkflow(workflow: EcrWorkflow): Promise<EcrWorkflow> {
  const response = await axios.post<EcrWorkflow>(`workflows/ecr/${workflow.id}/reject/`, {
    version: workflow.version
  })
  return response.data
}

/** Start publication of an approved workflow through the durable JIRA executor. */
export async function publishEcrWorkflow(
  workflow: EcrWorkflow,
  idempotencyKey: string
): Promise<EcrWorkflow> {
  return startExternalWrite(workflow, 'publish', idempotencyKey)
}

/** Resume an explicitly reconciled or safely resumable workflow with a new attempt key. */
export async function resumeEcrWorkflow(
  workflow: EcrWorkflow,
  idempotencyKey: string
): Promise<EcrWorkflow> {
  return startExternalWrite(workflow, 'resume', idempotencyKey)
}

async function startExternalWrite(
  workflow: EcrWorkflow,
  action: 'publish' | 'resume',
  idempotencyKey: string
): Promise<EcrWorkflow> {
  const response = await axios.post<EcrWorkflow>(
    `workflows/ecr/${workflow.id}/${action}/`,
    { version: workflow.version },
    { headers: { 'Idempotency-Key': idempotencyKey } }
  )
  return response.data
}
