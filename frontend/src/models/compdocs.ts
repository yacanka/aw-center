export interface ICompDoc {
  id?: number
  project?: string
  panel?: string
  discipline?: string
  title?: string
  [key: string]: unknown
}

export interface IColumnSetting {
  key: string
  title: string
  visible: boolean
}

export interface IHistory {
  history_date?: string
  history_type?: string
  history_user?: string
  [key: string]: unknown
}

export interface InvalidDocument {
  filename?: string
  reason?: string
  [key: string]: unknown
}
