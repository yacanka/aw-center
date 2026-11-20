import { apiClient } from '@/shared/api/http'
import type { Job, JobStatus } from '@/features/jobs/api/jobs'
import type { IJiraField } from '../models/jira'
import type { JiraSubtaskItem } from './jiraSubtasks'

export interface MinutesAction {
  no: string
  action_item: string
  assignee: string
  responsible: string
  due_date: string
}

export async function readMeetingMinutes(file: File): Promise<Job> {
  const data = new FormData()
  data.append('file', file)
  return (await apiClient.post<Job>('integrations/jira/meeting-minutes/jobs/', data)).data
}

const actionsPath = (draftId: string) => `integrations/jira/meeting-minutes/${draftId}/actions/`

export async function fetchMeetingActions(draftId: string) {
  return (
    await apiClient.get<
      { job_id: string; status: JobStatus } | { actions: MinutesAction[]; fields: IJiraField[] }
    >(actionsPath(draftId))
  ).data
}

export async function publishMeetingActions(draftId: string, items: JiraSubtaskItem[]) {
  return (await apiClient.post<Job>(actionsPath(draftId), { items })).data
}
