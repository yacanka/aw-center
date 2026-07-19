import axios from 'axios'
import type { MediaConversionParameters } from '@/services/mediaTools'

export type JobStatus =
  'queued' | 'running' | 'cancel_requested' | 'cancelled' | 'succeeded' | 'failed'

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
  overall_score?: number
  passed?: number
  total?: number
  checks?: AnalysisCheckSummary[]
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
  retryable: boolean
  request_id: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  updated_at: string
  can_cancel: boolean
  can_retry: boolean
  download_url: string | null
  recovery_hint: string
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

/** Download an owned completed job artifact. */
export async function downloadJob(job: Job): Promise<void> {
  if (!job.download_url) return
  const response = await axios.get<Blob>(job.download_url, { responseType: 'blob' })
  downloadBlob(response.data, job.output_name || 'job-output')
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

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
