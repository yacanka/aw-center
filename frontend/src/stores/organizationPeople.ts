import axios from 'axios'
import { handleRequest } from '@/composables/promise'
import type { IPerson } from '@/models/orgs'
import { isAuthenticated } from '@/stores/user'
import { notifyError, notifySuccess } from '@/services/notify'
import {
  compactPaginationQuery,
  getPaginatedResults,
  getPaginationMeta,
  type PaginationQuery
} from '@/services/pagination'
import { API_PATHS } from '@/stores/apiPaths'
import { runOrganizationRequest } from '@/stores/organizationRequest'
import type { OrganizationState } from '@/stores/organizationState'

export type PeopleImportError = {
  name: string
  error: string | Record<string, unknown>
}

export type PeopleImportResult = {
  message: string
  error_list?: PeopleImportError[]
}

/** Load a cached or server-paginated people page. */
export async function fetchPeople(
  state: OrganizationState,
  forceRefresh = false,
  query: PaginationQuery = {}
): Promise<unknown> {
  if (!isAuthenticated()) return []
  if (canReuseRequest(state, forceRefresh, query)) return state.peopleRequest
  if (canReusePeople(state, forceRefresh, query)) return state.people
  state.loading = true
  state.peopleRequest = requestPeople(state, query)
  const response = await state.peopleRequest
  state.peoplePagination = getPaginationMeta<IPerson>(response) || state.peoplePagination
  return response
}

/** Search the people directory without replacing the active page. */
export async function searchPeople(
  searchText: string,
  pageSize = 10,
  signal?: AbortSignal
): Promise<IPerson[]> {
  const search = searchText.trim()
  if (!isAuthenticated() || !search) return []
  const response = await handleRequest<IPerson[]>(
    axios.get(`${API_PATHS.orgs}/people/`, {
      params: compactPaginationQuery({ search, page_size: pageSize }),
      signal
    }),
    () => undefined,
    () => undefined,
    undefined,
    { suppressAuthenticationWarning: true }
  )
  return getPaginatedResults<IPerson>(response)
}

/** Create a directory person. */
export async function createPerson(state: OrganizationState, data: IPerson): Promise<void> {
  await runOrganizationRequest<IPerson>(state, axios.post(peoplePath(), data), (created) => {
    state.people.unshift(created)
    notifySuccess('New person added successfully.')
  })
}

/** Update a directory person. */
export async function updatePerson(
  state: OrganizationState,
  id: number,
  data: IPerson
): Promise<void> {
  await runOrganizationRequest<IPerson>(state, axios.put(`${peoplePath()}${id}/`, data), (item) => {
    const index = state.people.findIndex((person) => person.id === id)
    if (index >= 0) state.people[index] = { ...state.people[index], ...item }
    notifySuccess('Updated successfully.')
  })
}

/** Delete a directory person. */
export async function deletePerson(state: OrganizationState, id: number): Promise<void> {
  await runOrganizationRequest<void>(state, axios.delete(`${peoplePath()}${id}/`), () => {
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
    axios.post(`${API_PATHS.orgs}/upload_people/`, file),
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

function requestPeople(state: OrganizationState, query: PaginationQuery): Promise<unknown> {
  return handleRequest<IPerson[]>(
    axios.get(peoplePath(), { params: compactPaginationQuery(query) }),
    (data) => {
      state.people = data
      state.peopleFetched = true
    },
    notifyError,
    () => {
      state.loading = false
      state.peopleRequest = null
    },
    { suppressAuthenticationWarning: true }
  )
}

function peoplePath(): string {
  return `${API_PATHS.orgs}/people/`
}
