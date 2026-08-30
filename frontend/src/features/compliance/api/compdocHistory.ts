import type { ICompDoc } from '@/features/compliance/models/compdocs'

type IdentifiedCompdoc = ICompDoc & { id: string }

/** Return whether an expanded document still needs its history loaded from the API. */
export function shouldLoadCompdocHistory(
  compdoc: ICompDoc,
  expanded?: boolean
): compdoc is IdentifiedCompdoc {
  return expanded === true && compdoc.id !== undefined && compdoc.history == null
}
