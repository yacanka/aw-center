import { apiClient } from '@/shared/api/http'
import type { IDcc } from '@/features/dcc/models/dcc'
import {
  compactPaginationQuery,
  getPaginationMeta,
  type PaginatedResponse,
  type PaginationMeta,
  type PaginationQuery
} from '@/shared/services/pagination'

export interface DccRecordPage {
  results: IDcc[]
  pagination: PaginationMeta
}

/** Load one server-authorized DCC page without retaining route state globally. */
export async function fetchDccRecords(query: PaginationQuery = {}): Promise<DccRecordPage> {
  const response = await apiClient.get<PaginatedResponse<IDcc>>('dcc/records/', {
    params: compactPaginationQuery(query)
  })
  return {
    results: response.data.results,
    pagination: getPaginationMeta<IDcc>(response) || { count: 0, next: null, previous: null }
  }
}
