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
  ubm_target_date: string
  ubm_delivery_date: string
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
  type?: string
  width?: number | string
  sorter?: boolean
  filter?: boolean
  ellipsis?: boolean
}

export interface ICompDocFieldsResponse {
  fields: ICompDocFieldMetadata[]
}

export interface IColumnSetting {
  key: string
  title?: string
  visible?: boolean
  width?: number | string
  sorter?: boolean
  filter?: boolean
  ellipsis?: boolean
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
