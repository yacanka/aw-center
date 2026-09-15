import { apiClient } from '@/shared/api/http'

export interface ResetPreview {
  counts: Record<string, number>
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
