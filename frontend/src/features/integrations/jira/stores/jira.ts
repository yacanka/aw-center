import { defineStore } from 'pinia'
import { notifyError } from '@/shared/services/notify'
import { formatApiError } from '@/shared/api/apiError'
import {
  connectJira,
  disconnectJira,
  fetchJiraConnection,
  type JiraAuthMethod,
  type JiraConnection
} from '@/features/integrations/jira/api/jiraSession'

export const useJiraStore = defineStore('jira', {
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
    async connectJira(
      credential: string,
      method: JiraAuthMethod = 'session_id'
    ): Promise<JiraConnection> {
      try {
        return (this.jiraConnection = await connectJira(credential, method))
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
  return { state: 'disconnected', user: null, expires_at: null }
}
