export interface IUser {
  displayName?: string
  emailAddress?: string
  [key: string]: unknown
}

export interface ISubtaskItem {
  summary?: string
  description?: string
  assignee?: string
  [key: string]: unknown
}

export interface ISubtaskListItem {
  title: string
  list: ISubtaskItem[]
}

export interface IJira {
  issue?: string
  status?: string
  fields?: Record<string, unknown>
  [key: string]: unknown
}
