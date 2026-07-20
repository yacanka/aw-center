import axios from 'axios'
import { saveBlobAsFile } from '@/services/download'
import type { MediaConversionParameters } from '@/services/mediaTools'

export type JobStatus =
  | 'awaiting_confirmation'
  | 'queued'
  | 'running'
  | 'cancel_requested'
  | 'cancelled'
  | 'succeeded'
  | 'failed'

export interface JobEvent {
  id: number
  status: JobStatus
  progress: number
  message: string
  code: string
  details: Record<string, unknown>
  created_at: string
}

export interface AnalysisCheckSummary {
  id: string
  title: string
  score: number
  status: 'success' | 'warning' | 'error'
}

export interface JobResultSummary {
  type?: string
  issue_key?: string
  project?: string
  overall_score?: number
  passed?: number
  total?: number
  checks?: AnalysisCheckSummary[]
  output_name?: string
  panel_count?: number
  template_ready?: boolean
  source_updated_at?: string
  missing_recommended_fields?: string[]
  warning_count?: number
}

export interface JobHandoff {
  id: string
  label: string
  description: string
  target_kind: string
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
  retry_of: string | null
  source_job: string | null
  workflow_run: string | null
  workflow_step: number | null
  retryable: boolean
  request_id: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  confirmation_expires_at: string | null
  updated_at: string
  can_cancel: boolean
  can_retry: boolean
  download_url: string | null
  recovery_hint: string
  handoffs: JobHandoff[]
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

/** List the authenticated user's newest durable jobs. */
export async function fetchJobs(page = 1, pageSize = 20): Promise<JobPage> {
  const response = await axios.get<JobPage>('/jobs/', { params: { page, page_size: pageSize } })
  return response.data
}

/** Fetch one owned job together with its bounded audit history. */
export async function fetchJob(jobId: string): Promise<Job> {
  const response = await axios.get<Job>(`/jobs/${jobId}/`)
  return response.data
}

/** Return durable worker availability and owner-scoped queue counts. */
export async function fetchJobSystemStatus(): Promise<JobSystemStatus> {
  const response = await axios.get<JobSystemStatus>('/jobs/system/')
  return response.data
}

/** Request cooperative cancellation for a durable job. */
export async function cancelJob(jobId: string): Promise<Job> {
  const response = await axios.post<Job>(`/jobs/${jobId}/cancel/`)
  return response.data
}

/** Queue a new attempt using a failed or cancelled job's immutable input. */
export async function retryJob(jobId: string): Promise<Job> {
  const response = await axios.post<Job>(`/jobs/${jobId}/retry/`)
  return response.data
}

/** Reuse a verified owned output as an allowlisted downstream job input. */
export async function createJobHandoff(jobId: string, handoffId: string): Promise<Job> {
  const response = await axios.post<Job>(`/jobs/${jobId}/handoffs/${handoffId}/`)
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
  const response = await axios.post<Job>('/media-tools/jobs/', createFormData(file, parameters), {
    headers: { 'Idempotency-Key': crypto.randomUUID() }
  })
  return response.data
}

/** Enqueue a durable local-model Word translation. */
export async function createWordTranslationJob(file: File, translateType: string): Promise<Job> {
  return enqueueFileJob('/word/jobs/translate/', file, { translate_type: translateType })
}

/** Enqueue private explainable Word document analysis. */
export async function createDocumentAnalysisJob(file: File, checkIds: string[]): Promise<Job> {
  return enqueueFileJob('/word/jobs/analyze/', file, { check_ids: JSON.stringify(checkIds) })
}

/** Enqueue durable cover-page generation from a validated workbook. */
export async function createCoverPageJob(file: File): Promise<Job> {
  return enqueueFileJob('/excel/jobs/cover-pages/', file)
}

/** Capture and dry-render one private DCC snapshot before worker exposure. */
export async function previewDccDocumentJob(sessionId: string, issueUrl: string): Promise<Job> {
  const response = await axios.post<Job>(
    '/dcc/jobs/create-document/preview/',
    { JSESSIONID: sessionId, url: issueUrl },
    { headers: { 'Idempotency-Key': crypto.randomUUID() } }
  )
  return response.data
}

/** Queue the exact owned DCC snapshot selected in its time-bounded preview. */
export async function confirmDccDocumentJob(jobId: string): Promise<Job> {
  const response = await axios.post<Job>(`/dcc/jobs/create-document/${jobId}/confirm/`)
  return response.data
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
