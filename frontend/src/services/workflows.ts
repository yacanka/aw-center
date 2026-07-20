import axios from 'axios'
import type { Job, JobStatus } from '@/services/jobs'

export type WorkflowStatus = Extract<
  JobStatus,
  'queued' | 'running' | 'cancel_requested' | 'cancelled' | 'succeeded' | 'failed'
>

export interface WorkflowRecipeStep {
  sequence: number
  kind: string
  label: string
}

export interface WorkflowRecipe {
  id: string
  title: string
  description: string
  input: {
    label: string
    help: string
    accept: string[]
  }
  steps: WorkflowRecipeStep[]
  parameters: WorkflowRecipeParameter[]
}

export interface WorkflowRecipeParameter {
  name: string
  label: string
  type: 'select'
  required: boolean
  options: Array<{ value: string; label: string }>
}

export interface WorkflowRunStep extends WorkflowRecipeStep {
  job: Job | null
}

export interface WorkflowRun {
  id: string
  recipe: string
  title: string
  status: WorkflowStatus
  progress: number
  message: string
  error_code: string
  recovery_hint: string
  input_name: string
  current_step: number
  total_steps: number
  request_id: string
  can_cancel: boolean
  steps: WorkflowRunStep[]
  created_at: string
  completed_at: string | null
  updated_at: string
}

interface WorkflowPage {
  count: number
  next: string | null
  previous: string | null
  results: WorkflowRun[]
}

/** List allowlisted workflow recipes available to the signed-in user. */
export async function fetchWorkflowRecipes(): Promise<WorkflowRecipe[]> {
  const response = await axios.get<WorkflowRecipe[]>('/jobs/workflows/recipes/')
  return response.data
}

/** List the newest owner-scoped workflow runs. */
export async function fetchWorkflowRuns(pageSize = 5): Promise<WorkflowPage> {
  const response = await axios.get<WorkflowPage>('/jobs/workflows/', {
    params: { page: 1, page_size: pageSize }
  })
  return response.data
}

/** Enqueue one idempotent file-backed workflow recipe. */
export async function createWorkflowRun(
  recipe: string,
  file: File,
  parameters: Record<string, string | null>,
  idempotencyKey: string
): Promise<WorkflowRun> {
  const formData = new FormData()
  formData.append('recipe', recipe)
  formData.append('file', file)
  Object.entries(parameters).forEach(([name, value]) => {
    if (value) formData.append(name, value)
  })
  const response = await axios.post<WorkflowRun>('/jobs/workflows/', formData, {
    headers: { 'Idempotency-Key': idempotencyKey }
  })
  return response.data
}

/** Cancel every active job belonging to an owned workflow run. */
export async function cancelWorkflowRun(workflowId: string): Promise<WorkflowRun> {
  const response = await axios.post<WorkflowRun>(`/jobs/workflows/${workflowId}/cancel/`)
  return response.data
}
