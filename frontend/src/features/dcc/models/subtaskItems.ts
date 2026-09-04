import type { ISubtaskItem } from './jira'
import type { JiraSubtaskItem } from '@/features/dcc/api/jiraSubtasks'

/** Translate saved dynamic columns without changing the user's persisted lists. */
export function toSubtaskRequest(item: ISubtaskItem): JiraSubtaskItem {
  const fields = { ...item.fields }
  const description = fields.description ?? item.description ?? ''
  const assignee = item.assignee || fields.assignee || ''
  const dueDate = fields.duedate ?? item.duedate ?? item.due_date
  delete fields.description
  delete fields.assignee
  delete fields.duedate
  return {
    summary: item.summary || '',
    description: String(description),
    assignee: String(assignee),
    due_date: dueDate ? String(dueDate) : null,
    fields
  }
}
