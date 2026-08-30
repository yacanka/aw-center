import { apiClient as axios } from '@/shared/api/http'
import { handleRequest } from '@/shared/composables/promise'
import type { IPerson } from '@/features/organization/models/orgs'
import { notifyError, notifySuccess } from '@/shared/services/notify'
import {
  compactPaginationQuery,
  getPaginatedResults,
  getPaginationMeta,
  type PaginationQuery
} from '@/shared/services/pagination'
import { organizationPath } from '@/shared/api/apiPaths'
import { runOrganizationRequest } from '@/features/organization/api/organizationRequest'
import type { OrganizationState } from '@/features/organization/composables/organizationState'

export type PeopleImportError = {
  name: string
  error: string | Record<string, unknown>
}

export type PeopleImportResult = {
  message: string
  error_list?: PeopleImportError[]
}

export type PeopleSearchPage = {
  results: IPerson[]
  count: number
  page: number
  hasMore: boolean
}

/** Load a cached or server-paginated people page. */
export async function fetchPeople(
  state: OrganizationState,
  forceRefresh = false,
  query: PaginationQuery = {}
): Promise<unknown> {
  if (!state.project) return []
  if (canReuseRequest(state, forceRefresh, query)) return state.peopleRequest
  if (canReusePeople(state, forceRefresh, query)) return state.people
  state.loading = true
  const requestId = ++state.peopleRequestId
  state.peopleRequest = requestPeople(state, query, requestId)
  const response = await state.peopleRequest
  if (requestId == state.peopleRequestId) updatePeoplePagination(state, response)
  return response
}

/** Search the people directory without replacing the active page. */
export async function searchPeople(
  state: OrganizationState,
  searchText: string,
  page = 1,
  pageSize = 10,
  signal?: AbortSignal
): Promise<PeopleSearchPage> {
  const search = searchText.trim()
  if (!state.project || !search) return emptySearchPage(page)
  const response = await handleRequest<IPerson[]>(
    axios.get(peoplePath(state), {
      params: compactPaginationQuery({ search, page, page_size: pageSize }),
      signal
    }),
    () => undefined,
    () => undefined,
    undefined,
    { suppressAuthenticationWarning: true }
  )
  return toSearchPage(response, page)
}

/** Create a directory person. */
export async function createPerson(state: OrganizationState, data: IPerson): Promise<void> {
  await runOrganizationRequest<IPerson>(
    state,
    axios.post(peoplePath(state), personPayload(data)),
    (created) => {
      state.people.unshift(created)
      notifySuccess('New person added successfully.')
    }
  )
}

/** Update a directory person. */
export async function updatePerson(
  state: OrganizationState,
  id: number,
  data: IPerson
): Promise<void> {
  await runOrganizationRequest<IPerson>(
    state,
    axios.put(peoplePath(state, id), personPayload(data)),
    (item) => {
      const index = state.people.findIndex((person) => person.id === id)
      if (index >= 0) state.people[index] = { ...state.people[index], ...item }
      notifySuccess('Updated successfully.')
    }
  )
}

/** Delete a directory person. */
export async function deletePerson(state: OrganizationState, id: number): Promise<void> {
  await runOrganizationRequest<void>(state, axios.delete(peoplePath(state, id)), () => {
    state.people = state.people.filter((person) => person.id !== id)
    notifySuccess('Deleted successfully.')
  })
}

/** Import people from a validated workbook. */
export async function uploadPeople(
  state: OrganizationState,
  file: FormData
): Promise<PeopleImportResult> {
  return runOrganizationRequest<PeopleImportResult>(
    state,
    axios.post(organizationPath(state.project, 'people', 'import'), file),
    (data) => notifySuccess(data.message)
  )
}

function canReuseRequest(
  state: OrganizationState,
  forceRefresh: boolean,
  query: PaginationQuery
): boolean {
  return Boolean(state.peopleRequest && !forceRefresh && !Object.keys(query).length)
}

function canReusePeople(
  state: OrganizationState,
  forceRefresh: boolean,
  query: PaginationQuery
): boolean {
  return state.peopleFetched && !forceRefresh && !Object.keys(query).length
}

function requestPeople(
  state: OrganizationState,
  query: PaginationQuery,
  requestId: number
): Promise<unknown> {
  return handleRequest<IPerson[]>(
    axios.get(peoplePath(state), { params: compactPaginationQuery(query) }),
    (data) => {
      if (requestId != state.peopleRequestId) return
      state.people = data
      state.peopleFetched = true
    },
    (message) => notifyPeopleRequestError(state, requestId, message),
    () => {
      if (requestId != state.peopleRequestId) return
      state.loading = false
      state.peopleRequest = null
    },
    { suppressAuthenticationWarning: true }
  )
}

function notifyPeopleRequestError(
  state: OrganizationState,
  requestId: number,
  message: string
): void {
  if (requestId == state.peopleRequestId) notifyError(message)
}

function updatePeoplePagination(state: OrganizationState, response: unknown): void {
  state.peoplePagination = getPaginationMeta<IPerson>(response) || state.peoplePagination
}

function toSearchPage(response: unknown, page: number): PeopleSearchPage {
  const results = getPaginatedResults<IPerson>(response)
  const metadata = getPaginationMeta<IPerson>(response)
  return {
    results,
    count: metadata?.count ?? results.length,
    page,
    hasMore: Boolean(metadata?.next)
  }
}

function emptySearchPage(page: number): PeopleSearchPage {
  return { results: [], count: 0, page, hasMore: false }
}

function peoplePath(state: OrganizationState, personId?: number): string {
  return organizationPath(state.project, 'people', ...(personId === undefined ? [] : [personId]))
}

function personPayload(person: IPerson) {
  return { person_id: person.person_id, name: person.name, email: person.email }
}
