export type JiraFieldInputType = 'date' | 'number' | 'person' | 'text'

export interface IJiraField {
  id: string
  name: string
  required?: boolean
  hasDefaultValue?: boolean
  schema?: Record<string, unknown>
  allowedValues?: Array<Record<string, unknown>>
}

export type JiraFieldPrimitive = string | number
export type JiraFieldValue = JiraFieldPrimitive | JiraFieldPrimitive[] | null

/** Persisted list format shared with the original Subtask Generator. */
export interface ISubtaskItem {
  summary?: string
  description?: string
  assignee?: string
  fields?: Record<string, JiraFieldValue>
  [key: string]: unknown
}

export interface ISubtaskListItem {
  title: string
  list: ISubtaskItem[]
  fields?: IJiraField[]
}
