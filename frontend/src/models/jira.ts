export interface IUser {
  displayName?: string
  emailAddress?: string
  [key: string]: unknown
}

export interface IJiraField {
  id: string
  name: string
  required?: boolean
  schema?: Record<string, unknown>
  allowedValues?: Array<Record<string, unknown>>
}

export interface ISubtaskItem {
  summary?: string
  description?: string
  assignee?: string
  fields?: Record<string, string | null>
  [key: string]: unknown
}

export interface ISubtaskListItem {
  title: string
  list: ISubtaskItem[]
  fields?: IJiraField[]
}

export interface IJira {
  issue?: string
  status?: string
  fields?: Record<string, string | null>
  [key: string]: unknown
}
