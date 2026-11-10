import { apiClient as axios } from '@/shared/api/http'
import { saveBlobAsFile } from '@/shared/services/download'
import type { MediaConversionParameters } from '@/features/tools/api/mediaTools'
import type { JobResultSummary } from '@/features/jobs/api/jobSummaries'

export type JobStatus =
  | 'awaiting_confirmation'
  | 'queued'
  | 'running'
  | 'cancel_requested'
  | 'cancelled'
  | 'succeeded'
  | 'failed'
  | 'reconciliation_required'

export interface JobEvent {
  id: number
  status: JobStatus
  progress: number
  message: string
  code: string
  details: Record<string, unknown>
  created_at: string
}

export interface JobJiraDraftReference {
  id: string
  status: string
  version: number
  jira_issue_key: string
}

export interface Job {
  id: string
  kind: string
  title: string
  status: JobStatus
  progress: number
  message: string
  error_code: string
  input_name: string
  output_name: string
  result_summary: JobResultSummary
  attempt: number
  max_attempts: number
  source_job: string | null
  workflow_run: string | null
  workflow_step: number | null
  request_id: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  confirmation_expires_at: string | null
  updated_at: string
  can_cancel: boolean
  download_url: string | null
  recovery_hint: string
  jira_draft: JobJiraDraftReference | null
  events?: JobEvent[]
}

interface JobPage {
  count: number
  next: string | null
  previous: string | null
  results: Job[]
}

export interface JobSystemStatus {
  available: boolean
  active_workers: number
  counts: Partial<Record<JobStatus, number>>
}

const ACTIVE_JOB_STATUSES: ReadonlySet<JobStatus> = new Set([
  'queued',
  'running',
  'cancel_requested'
])

/** Return true only while polling can observe another worker transition. */
export function isActiveJobStatus(status: JobStatus | undefined): boolean {
  return Boolean(status && ACTIVE_JOB_STATUSES.has(status))
}

/** Treat an ambiguous external write as a failed terminal result in the UI. */
export function isFailedJobStatus(status: JobStatus): boolean {
  return status === 'failed' || status === 'reconciliation_required'
}

/** List the authenticated user's newest durable jobs. */
export async function fetchJobs(page = 1, pageSize = 20): Promise<JobPage> {
  const response = await axios.get<JobPage>('jobs/', { params: { page, page_size: pageSize } })
  return response.data
}

/** Fetch one owned job together with its bounded audit history. */
export async function fetchJob(jobId: string): Promise<Job> {
  const response = await axios.get<Job>(`jobs/${jobId}/`)
  return response.data
}

/** Return durable worker availability and owner-scoped queue counts. */
export async function fetchJobSystemStatus(): Promise<JobSystemStatus> {
  const response = await axios.get<JobSystemStatus>('jobs/system/')
  return response.data
}

/** Request cooperative cancellation for a durable job. */
export async function cancelJob(jobId: string): Promise<Job> {
  const response = await axios.post<Job>(`jobs/${jobId}/cancel/`)
  return response.data
}

/** Download an owned completed job artifact. */
export async function downloadJob(job: Job): Promise<void> {
  if (!job.download_url) return
  const response = await axios.get<Blob>(job.download_url, { responseType: 'blob' })
  saveBlobAsFile(response.data, job.output_name || 'job-output')
}

/** Enqueue a validated media conversion with request idempotency. */
export async function createMediaJob(
  file: File,
  parameters: MediaConversionParameters
): Promise<Job> {
  const response = await axios.post<Job>('tools/media/jobs/', createFormData(file, parameters), {
    headers: { 'Idempotency-Key': crypto.randomUUID() }
  })
  return response.data
}

/** Enqueue a durable local-model Word translation. */
export async function createWordTranslationJob(file: File, translateType: string): Promise<Job> {
  return enqueueFileJob('tools/word/jobs/translate/', file, { translate_type: translateType })
}

/** Enqueue private explainable Word document analysis. */
export async function createDocumentAnalysisJob(file: File, checkIds: string[]): Promise<Job> {
  return enqueueFileJob('tools/word/jobs/analyze/', file, { check_ids: JSON.stringify(checkIds) })
}

/** Enqueue durable cover-page generation from a validated workbook. */
export async function createCoverPageJob(file: File): Promise<Job> {
  return enqueueFileJob('tools/excel/jobs/cover-pages/', file)
}

async function enqueueFileJob(
  path: string,
  file: File,
  parameters: Record<string, unknown> = {}
): Promise<Job> {
  const response = await axios.post<Job>(path, createFormData(file, parameters), {
    headers: { 'Idempotency-Key': crypto.randomUUID() }
  })
  return response.data
}

function createFormData(file: File, parameters: object): FormData {
  const formData = new FormData()
  formData.append('file', file)
  Object.entries(parameters).forEach(([key, value]) => appendValue(formData, key, value))
  return formData
}

function appendValue(formData: FormData, key: string, value: unknown): void {
  if (value === null || value === undefined || value === '') return
  formData.append(key, String(value))
}
