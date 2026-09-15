import { apiClient } from '@/shared/api/http'

export interface ResetPreview {
  counts: Record<string, number>
  prepared: boolean
  ready: boolean
  blockers: {
    jobs: { id: string; kind: string; status: string }[]
    job_count: number
    uncertain_jobs: { id: string; kind: string; status: string }[]
    uncertain_job_count: number
    allocations: {
      id: string
      project__slug: string
      status: string
      current_job_id: string | null
    }[]
    allocation_count: number
    notification_count: number
  }
  confirmation_phrase: string
  confirmation_token: string
}

const path = 'developer/compliance-organization-reset/'

export async function previewTestDataReset(): Promise<ResetPreview> {
  return (await apiClient.get<ResetPreview>(path)).data
}

export async function resetTestData(preview: ResetPreview, phrase: string): Promise<void> {
  await apiClient.post(path, {
    confirmation_token: preview.confirmation_token,
    confirmation_phrase: phrase
  })
}

export async function prepareTestDataReset(preview: ResetPreview): Promise<ResetPreview> {
  return (
    await apiClient.post<ResetPreview>(path, {
      action: 'prepare',
      confirmation_token: preview.confirmation_token
    })
  ).data
}

export async function releaseTestDataReset(preview: ResetPreview): Promise<ResetPreview> {
  return (
    await apiClient.post<ResetPreview>(path, {
      action: 'release',
      confirmation_token: preview.confirmation_token
    })
  ).data
}
