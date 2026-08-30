import { apiClient } from '@/shared/api/http'
import { API_PATHS } from '@/shared/api/apiPaths'

export type JiraConnection = {
  state: 'connected' | 'disconnected'
  expires_at: string | null
}

export async function fetchJiraConnection(): Promise<JiraConnection> {
  return (await apiClient.get<JiraConnection>(`${API_PATHS.jiraSession}/`)).data
}

export async function connectJira(credential: string): Promise<JiraConnection> {
  return (
    await apiClient.post<JiraConnection>(`${API_PATHS.jiraSession}/`, {
      JSESSIONID: credential
    })
  ).data
}

export async function disconnectJira(): Promise<void> {
  await apiClient.delete(`${API_PATHS.jiraSession}/`)
}
