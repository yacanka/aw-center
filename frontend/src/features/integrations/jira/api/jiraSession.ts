import { apiClient } from '@/shared/api/http'
import { API_PATHS } from '@/shared/api/apiPaths'

export type JiraAuthMethod = 'session_id' | 'personal_access_token'

export type JiraConnection = {
  state: 'connected' | 'disconnected'
  user: { username: string; display_name: string } | null
  expires_at: string | null
}

export async function fetchJiraConnection(): Promise<JiraConnection> {
  return (await apiClient.get<JiraConnection>(`${API_PATHS.jiraSession}/`)).data
}

export async function connectJira(
  credential: string,
  method: JiraAuthMethod = 'session_id'
): Promise<JiraConnection> {
  return (
    await apiClient.post<JiraConnection>(
      `${API_PATHS.jiraSession}/`,
      method === 'personal_access_token'
        ? { personal_access_token: credential }
        : { JSESSIONID: credential }
    )
  ).data
}

export async function disconnectJira(): Promise<void> {
  await apiClient.delete(`${API_PATHS.jiraSession}/`)
}
