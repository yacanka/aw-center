export interface ICompDoc {
  id?: string
  source_history_id?: number
  change_reason?: string
  project?: string
  panel: string | null
  discipline?: string
  title?: string
  name: string
  signature_panel: string[]
  ata: string | null
  cover_page?: string
  cover_page_no: string
  cover_page_issue: string
  tech_doc_no: string
  tech_doc_issue: string
  delivered_tech_doc_issue: string
  tech_doc_no_2: string
  tech_doc_issue_2: string
  delivered_tech_doc_issue_2: string
  responsible: string
  cat: string | null
  moc: string | null
  mom_no: string
  requirements: string[]
  status_flow: IStatusFlow[]
  status: string
  owner?: number | null
  owner_group?: number | null
  next_action_due_date?: string | null
  is_archived?: boolean
  archived_at?: string | null
  archive_reason?: string
  ubm_target_date: string | null
  ubm_delivery_date: string | null
  path: string
  notes: string
  authority_sharing_number: string
  created_time: string
  history?: IHistory[] | null
  [key: string]: unknown
}

export interface IStatusFlow {
  date: string
  status: string
  note?: string
}

export interface ICompDocFieldMetadata {
  key: string
  label: string
  type: string
  width: number
  filter_kind: CompDocFilterKind
  sortable: boolean
  default_visible: boolean
  ellipsis: boolean
  choices: ICompDocFieldChoice[]
  option_source: string | null
}

export interface ICompDocFieldsResponse {
  schema_version: number
  project: string
  fields: ICompDocFieldMetadata[]
}

export interface IColumnSetting {
  key: string
  width: number
  sorter: boolean
  filter: boolean
  ellipsis: boolean
}

export type CompDocFilterKind = 'none' | 'text' | 'select' | 'date' | 'number' | 'boolean'

export interface ICompDocFieldChoice {
  value: string | number | boolean
  label: string
}

export interface IHistory {
  history_date: string
  history_type: string
  history_user: string
  [key: string]: unknown
}

export interface ICompDocActivity {
  type: 'workflow' | 'review' | 'approval' | 'history'
  occurred_at: string
  actor: string
  reason: string
  status?: string
  previous_status?: string
  changes?: Array<{
    field: string
    changed: boolean
    old?: unknown
    new?: unknown
  }>
}

export interface InvalidDocument {
  filename?: string
  reason?: string
  [key: string]: unknown
}
