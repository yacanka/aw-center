import { apiClient as axios } from '@/shared/api/http'
import type { Job } from '@/features/jobs/api/jobs'

/** Capture and dry-render one private DCC snapshot before worker exposure. */
export async function previewDccDocumentJob(issueUrl: string): Promise<Job> {
  const response = await axios.post<Job>(
    'dcc/jobs/create-document/preview/',
    { url: issueUrl },
    { headers: { 'Idempotency-Key': crypto.randomUUID() } }
  )
  return response.data
}

/** Queue the reviewed snapshot with its exact warning acknowledgement. */
export async function confirmDccDocumentJob(jobId: string, warningCodes: string[]): Promise<Job> {
  const response = await axios.post<Job>(`dcc/jobs/create-document/${jobId}/confirm/`, {
    acknowledged_warning_codes: warningCodes
  })
  return response.data
}
