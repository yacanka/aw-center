import type { ICompDoc } from '@/models/compdocs'

export type CompDocUpdatePayload = Omit<ICompDoc, 'status_flow'>

/** Remove the read-only workflow projection from a regular document update. */
export function buildCompdocUpdatePayload(document: ICompDoc): CompDocUpdatePayload {
  const { status_flow: _statusFlow, ...payload } = document
  return payload
}
