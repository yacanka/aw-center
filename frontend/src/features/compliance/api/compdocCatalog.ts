import type { ICompDoc } from '@/features/compliance/models/compdocs'

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

export const statusColors: Record<string, StatusColorSet> = {
  to_be_issued: colorSet('#94a3b8'),
  missing_target: colorSet('#64748b'),
  airworthiness_review: colorSet('#f97316'),
  'to_be_re-submitted': colorSet('#3b82f6'),
  to_be_updated: colorSet('#3b82f6'),
  authority_review: colorSet('#eab308'),
  authority_approved: colorSet('#C6EFCE'),
  delayed: colorSet('#FFC7CE')
}

export const mocOptions: CompdocOption[] = [
  ...Array.from({ length: 10 }, (_, value) => ({ value: String(value), label: String(value) })),
  { value: 'M', label: 'M' }
]

const EMPTY_COMPDOC: ICompDoc = {
  name: '',
  panel: null,
  panel_name: '',
  signature_panel: [],
  ata: null,
  cover_page_no: '',
  cover_page_issue: '',
  number: '',
  issue: '',
  responsible: '',
  cat: null,
  moc: null,
  mom_no: '',
  requirements: [],
  status_flow: [],
  status: '',
  target_date: null,
  revised_target_date: null,
  release_date: null,
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
