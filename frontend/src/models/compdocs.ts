export interface ICompDoc {
  id?: string
  source_history_id?: number
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

export interface CompDocBulkDeleteRequest {
  confirmation: string
  expected_count: number
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

export interface InvalidDocument {
  filename?: string
  reason?: string
  [key: string]: unknown
}
