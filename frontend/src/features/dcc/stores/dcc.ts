import { defineStore } from 'pinia'
import { notifyError } from '@/shared/services/notify'
import { formatApiError } from '@/shared/api/apiError'
import {
  connectJira,
  disconnectJira,
  fetchJiraConnection,
  type JiraConnection
} from '@/features/dcc/api/jiraSession'

export const useDccStore = defineStore('dcc', {
  state: () => ({
    jiraConnection: disconnectedJiraConnection() as JiraConnection
  }),
  getters: {
    isJiraConnected: (state) => state.jiraConnection.state === 'connected',
    getJiraConnection: (state) => state.jiraConnection
  },
  actions: {
    /** Load the public, credential-free JIRA connection state. */
    async fetchJiraConnection(): Promise<JiraConnection> {
      try {
        return (this.jiraConnection = await fetchJiraConnection())
      } catch (error) {
        notifyError(formatApiError(error))
        throw error
      }
    },
    /** Exchange a one-time credential for an opaque server-side JIRA connection. */
    async connectJira(credential: string): Promise<JiraConnection> {
      try {
        return (this.jiraConnection = await connectJira(credential))
      } catch (error) {
        notifyError(formatApiError(error))
        throw error
      }
    },
    /** Revoke the opaque server-side JIRA connection. */
    async disconnectJira(): Promise<void> {
      try {
        await disconnectJira()
        this.jiraConnection = disconnectedJiraConnection()
      } catch (error) {
        notifyError(formatApiError(error))
        throw error
      }
    }
  }
})

function disconnectedJiraConnection(): JiraConnection {
  return { state: 'disconnected', expires_at: null }
}
