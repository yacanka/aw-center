import type { ICompDoc } from '@/models/compdocs'

export interface CompdocOption {
  value: string
  label: string
}

export interface StatusColorSet {
  color: string
  color25: string
  color50: string
  color75: string
}

const BASE_STATUS_OPTIONS: CompdocOption[] = [
  { value: 'to_be_issued', label: 'To be Issued' },
  { value: 'airworthiness_review', label: 'Airworthiness Review' },
  { value: 'to_be_re-submitted', label: 'To be Re-Submitted' },
  { value: 'to_be_updated', label: 'To be Updated' },
  { value: 'authority_review', label: 'Authority Review' },
  { value: 'authority_approved', label: 'Authority Approved' }
]

export const statusOptions: CompdocOption[] = [
  ...BASE_STATUS_OPTIONS,
  { value: 'delayed', label: 'Delayed' }
]

export const statusColors: Record<string, StatusColorSet> = {
  to_be_issued: colorSet('#FFC7CE'),
  airworthiness_review: colorSet('#FFEB9C'),
  'to_be_re-submitted': colorSet('#ED7D31'),
  to_be_updated: colorSet('#FFF2CC'),
  authority_review: colorSet('#00B0F0'),
  authority_approved: colorSet('#C6EFCE'),
  delayed: colorSet('#FFC7CE')
}

export const mocOptions: CompdocOption[] = [
  ...Array.from({ length: 10 }, (_, value) => ({ value: String(value), label: String(value) })),
  { value: 'M', label: 'M' }
]

export const catOptions: CompdocOption[] = [
  { value: '1', label: '1' },
  { value: '2', label: '2' },
  { value: '3', label: '3' },
  { value: 'not_retained', label: 'Not Retained' },
  { value: 'retained', label: 'Retained' }
]

const EMPTY_COMPDOC: ICompDoc = {
  name: '',
  panel: null,
  signature_panel: [],
  ata: null,
  cover_page_no: '',
  cover_page_issue: '',
  tech_doc_no: '',
  tech_doc_issue: '',
  delivered_tech_doc_issue: '',
  tech_doc_no_2: '',
  tech_doc_issue_2: '',
  delivered_tech_doc_issue_2: '',
  responsible: '',
  cat: null,
  moc: null,
  mom_no: '',
  requirements: [],
  status_flow: [],
  status: '',
  ubm_target_date: '',
  ubm_delivery_date: '',
  path: '',
  notes: '',
  authority_sharing_number: '',
  created_time: '',
  history: []
}

/** Create a complete editable compliance-document draft with isolated arrays. */
export function createEmptyCompdoc(): ICompDoc {
  return {
    ...EMPTY_COMPDOC,
    signature_panel: [],
    requirements: [],
    status_flow: [],
    history: []
  }
}

function colorSet(color: string): StatusColorSet {
  return { color, color25: `${color}40`, color50: `${color}80`, color75: `${color}bf` }
}
