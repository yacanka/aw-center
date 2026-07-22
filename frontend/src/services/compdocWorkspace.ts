import type { ICompDoc } from '@/models/compdocs'

/** Convert a stored workflow status into an operator-facing label. */
export function humanizeCompdocStatus(status: unknown): string {
  const words = String(status || 'unknown')
    .replaceAll('_', ' ')
    .replaceAll('-', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Return the most useful stable reference for a compliance document. */
export function getCompdocReference(document: ICompDoc): string {
  return document.tech_doc_no || document.cover_page_no || document.name
}

/** Join present values without displaying empty separators. */
export function joinCompdocValues(values: unknown[], fallback = 'Not assigned'): string {
  const presentValues = values
    .map(String)
    .map((value) => value.trim())
    .filter(Boolean)
  return presentValues.join(', ') || fallback
}
