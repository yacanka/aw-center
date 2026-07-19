import type { IPerson, IPanel, IProject, IResponsible } from '@/models/orgs'
import type { PaginationMeta } from '@/services/pagination'

export interface OrganizationState {
  loading: boolean
  project: string
  projects: IProject[]
  panels: IPanel[]
  responsibles: IResponsible[]
  people: IPerson[]
  peoplePagination: PaginationMeta
  peopleFetched: boolean
  peopleRequest: Promise<unknown> | null
}

/** Create isolated organization state for one Pinia instance. */
export function createOrganizationState(): OrganizationState {
  return {
    loading: false,
    project: '',
    projects: [],
    panels: [],
    responsibles: [],
    people: [],
    peoplePagination: { count: 0, next: null, previous: null },
    peopleFetched: false,
    peopleRequest: null
  }
}
