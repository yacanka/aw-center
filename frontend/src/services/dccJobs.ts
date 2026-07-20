import axios from 'axios'
import type { Job } from '@/services/jobs'

export interface DccCompdocSelection {
  project: string
  documentIds: string[]
}

/** Capture and dry-render one private DCC snapshot before worker exposure. */
export async function previewDccDocumentJob(
  sessionId: string,
  issueUrl: string,
  selection?: DccCompdocSelection
): Promise<Job> {
  const response = await axios.post<Job>(
    '/dcc/jobs/create-document/preview/',
    {
      JSESSIONID: sessionId,
      url: issueUrl,
      compdoc_project: selection?.project || '',
      compdoc_ids: selection?.documentIds || []
    },
    { headers: { 'Idempotency-Key': crypto.randomUUID() } }
  )
  return response.data
}

/** Queue the reviewed snapshot with its exact warning acknowledgement. */
export async function confirmDccDocumentJob(jobId: string, warningCodes: string[]): Promise<Job> {
  const response = await axios.post<Job>(`/dcc/jobs/create-document/${jobId}/confirm/`, {
    acknowledged_warning_codes: warningCodes
  })
  return response.data
}

/** Derive a CompDoc-enriched preview from the same verified JIRA snapshot. */
export async function applyDccCompdocRecommendations(
  jobId: string,
  documentIds: string[]
): Promise<Job> {
  const response = await axios.post<Job>(
    `/dcc/jobs/create-document/${jobId}/compdoc-recommendations/`,
    { compdoc_ids: documentIds },
    { headers: { 'Idempotency-Key': crypto.randomUUID() } }
  )
  return response.data
}
