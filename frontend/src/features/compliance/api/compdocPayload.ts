import type { ICompDoc } from '@/features/compliance/models/compdocs'

export interface CompDocWritePayload {
  version?: number
  panel: number | null
  cover_page: { number: string; issue: string; version?: number }
  name: string
  signature_panel: string[]
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
  path: string
  notes: string
  change_reason?: string
}

export type CompDocCreatePayload = Omit<CompDocWritePayload, 'version' | 'change_reason'>
export type CompDocUpdatePayload = CompDocWritePayload

/** Build the explicit create contract and omit every server-owned projection. */
export function buildCompdocCreatePayload(document: ICompDoc): CompDocCreatePayload {
  const {
    version: _version,
    change_reason: _changeReason,
    ...payload
  } = buildWritePayload(document)
  return payload
}

/** Build a versioned update without leaking list, audit, ownership, or workflow projections. */
export function buildCompdocUpdatePayload(document: ICompDoc): CompDocUpdatePayload {
  return buildWritePayload(document)
}

function buildWritePayload(document: ICompDoc): CompDocWritePayload {
  return compact({
    version: document.version,
    panel: document.panel,
    cover_page: compact({
      number: document.cover_page_no,
      issue: document.cover_page_issue,
      version: document.cover_page_version
    }) as CompDocWritePayload['cover_page'],
    name: document.name,
    signature_panel: document.signature_panel,
    tech_doc_no: document.tech_doc_no,
    tech_doc_issue: document.tech_doc_issue,
    delivered_tech_doc_issue: document.delivered_tech_doc_issue,
    tech_doc_no_2: document.tech_doc_no_2,
    tech_doc_issue_2: document.tech_doc_issue_2,
    delivered_tech_doc_issue_2: document.delivered_tech_doc_issue_2,
    responsible: document.responsible,
    cat: document.cat,
    moc: document.moc,
    mom_no: document.mom_no,
    requirements: document.requirements,
    path: document.path,
    notes: document.notes,
    change_reason: document.change_reason
  }) as CompDocWritePayload
}

function compact<T extends Record<string, unknown>>(value: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => item !== undefined)
  ) as Partial<T>
}
