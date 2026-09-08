import { apiClient } from '@/shared/api/http'
import { compdocCollectionPath } from '@/shared/api/apiPaths'
import { getPaginatedResults, getPaginationMeta } from '@/shared/services/pagination'

export type CompdocOptionKind = 'panel' | 'user' | 'group'

export interface CompdocReferenceOption {
  id: number
  label: string
  name?: string
  username?: string
  ata?: string
}

export interface CompdocPanelReference extends CompdocReferenceOption {
  name: string
  ata: string
}

/** Load all bounded project-scoped selector values from the compliance API. */
export async function fetchCompdocOptions(
  project: string,
  kind: CompdocOptionKind
): Promise<CompdocReferenceOption[]> {
  const path = `${compdocCollectionPath(project)}options/`
  const results: CompdocReferenceOption[] = []
  let page = 1

  while (true) {
    const response = await apiClient.get<unknown>(path, {
      params: { kind, page, page_size: 200 }
    })
    const current = getPaginatedResults<CompdocReferenceOption>(response.data)
    const pagination = getPaginationMeta<CompdocReferenceOption>(response.data)
    if (!pagination) throw new Error('The compliance option response is invalid.')
    results.push(...current)
    if (!pagination.next || results.length >= pagination.count || !current.length) return results
    page += 1
  }
}

export function isCompdocPanelReference(
  option: CompdocReferenceOption
): option is CompdocPanelReference {
  return typeof option.name === 'string' && typeof option.ata === 'string'
}
