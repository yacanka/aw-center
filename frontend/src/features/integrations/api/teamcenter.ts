import { API_PATHS } from '@/shared/api/apiPaths'
import { apiClient } from '@/shared/api/http'
import type { Job } from '@/features/jobs/api/jobs'

export interface TeamcenterStatus {
  configured: boolean
  auth_mode: string
  service_root: string
  tls_verification_enabled: boolean
}

export interface TeamcenterObjectReference {
  uid: string
  type?: string
}

export interface TeamcenterPropertyUpdate {
  object: TeamcenterObjectReference
  properties: Record<string, string[]>
}

/** Returns non-secret Teamcenter integration readiness. */
export async function fetchTeamcenterStatus(): Promise<TeamcenterStatus> {
  return (await apiClient.get<TeamcenterStatus>(`${API_PATHS.teamcenter}/status/`)).data
}

/** Verifies the configured Teamcenter account and web-tier connection. */
export async function probeTeamcenter(): Promise<{ connected: boolean }> {
  return (await apiClient.post<{ connected: boolean }>(`${API_PATHS.teamcenter}/probe/`)).data
}

/** Returns saved queries visible to the configured Teamcenter account. */
export async function fetchTeamcenterSavedQueries(): Promise<Record<string, unknown>> {
  return (await apiClient.get<Record<string, unknown>>(`${API_PATHS.teamcenter}/saved-queries/`))
    .data
}

/** Loads a bounded set of Teamcenter object UIDs. */
export async function loadTeamcenterObjects(uids: string[]): Promise<Record<string, unknown>> {
  return (
    await apiClient.post<Record<string, unknown>>(`${API_PATHS.teamcenter}/objects/load/`, { uids })
  ).data
}

/** Queue an administrator-approved external write with request idempotency. */
export async function enqueueTeamcenterPropertyUpdate(
  updates: TeamcenterPropertyUpdate[],
  idempotencyKey: string
): Promise<Job> {
  const response = await apiClient.post<Job>(
    `${API_PATHS.teamcenter}/property-update-jobs/`,
    { updates },
    { headers: { 'Idempotency-Key': idempotencyKey } }
  )
  return response.data
}
