import type { ICompDoc } from '@/features/compliance/models/compdocs'

export interface CompDocWritePayload {
  version?: number
  panel: number | null
  ata: string | null
  cover_page: { number: string; issue: string; version?: number }
  name: string
  signature_panel: string[]
  number: string
  issue: string
  responsible: string
  cat: string | null
  moc: string | null
  mom_no: string
  requirements: string[]
  target_date: string | null
  revised_target_date: string | null
  release_date: string | null
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
    ata: document.ata,
    cover_page: compact({
      number: document.cover_page_no,
      issue: document.cover_page_issue,
      version: document.cover_page_version
    }) as CompDocWritePayload['cover_page'],
    name: document.name,
    signature_panel: document.signature_panel,
    number: document.number,
    issue: document.issue,
    responsible: document.responsible,
    cat: document.cat,
    moc: document.moc,
    mom_no: document.mom_no,
    requirements: document.requirements,
    target_date: document.target_date || null,
    revised_target_date: document.revised_target_date || null,
    release_date: document.release_date || null,
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
