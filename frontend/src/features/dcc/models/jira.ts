export type JiraFieldInputType =
  'date' | 'datetime' | 'boolean' | 'number' | 'person' | 'text' | 'unsupported'

export interface IJiraField {
  id: string
  name: string
  supported?: boolean
  required?: boolean
  hasDefaultValue?: boolean
  schema?: Record<string, unknown>
  allowedValues?: Array<Record<string, unknown>>
}

export type JiraFieldPrimitive = string | number | boolean
export interface JiraFieldReference {
  id?: string | number
  value?: string | number
  name?: string
  key?: string
  accountId?: string
  child?: JiraFieldReference
}
export type JiraFieldScalar = JiraFieldPrimitive | JiraFieldReference
export type JiraFieldValue = JiraFieldScalar | JiraFieldScalar[] | null

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
