export interface IDdf {
  id?: number
  project: string
  doc_name: string
  doc_no: string
  doc_issue: string
  date: string
  commentor: string
  comments: string[][]
  comment_types: string[]
  path?: string
}
