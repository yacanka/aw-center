import { inject, provide, reactive, type InjectionKey } from 'vue'
import { apiClient } from '@/shared/api/http'
import type { IGroup, IPermission, IUser } from '@/features/session/models/auth'
import { handleRequest } from '@/shared/composables/promise'
import { notifyError, notifySuccess } from '@/shared/services/notify'
import {
  compactPaginationQuery,
  getPaginationMeta,
  type PaginationMeta,
  type PaginationQuery
} from '@/shared/services/pagination'

interface UserAdministrationState {
  users: IUser[]
  permissions: IPermission[]
  groups: IGroup[]
  usersPagination: PaginationMeta
  permissionsPagination: PaginationMeta
  groupsPagination: PaginationMeta
  permissionsLoaded: boolean
  groupsLoaded: boolean
  loading: boolean
  requestVersion: number
}

export interface UserAdministrationController extends UserAdministrationState {
  readonly getUsers: IUser[]
  readonly getPermissions: IPermission[]
  readonly getGroups: IGroup[]
  readonly isLoading: boolean
  clearList(): void
  fetchUsers(query?: PaginationQuery): Promise<void>
  updateUser(id: number, data: IUser): Promise<void>
  deleteUser(id: number): Promise<void>
  fetchPermissions(query?: PaginationQuery): Promise<void>
  fetchGroups(query?: PaginationQuery): Promise<void>
  saveGroup(id: number | undefined, name: string, permissionIds: number[]): Promise<void>
  deleteGroup(id: number): Promise<void>
}

const controllerKey: InjectionKey<UserAdministrationController> = Symbol(
  'user-administration-controller'
)
const usersPath = 'users'

/** Create administrator table state scoped to the users route. */
export function createUserAdministrationController(): UserAdministrationController {
  const state = reactive<UserAdministrationState>({
    users: [],
    permissions: [],
    groups: [],
    usersPagination: emptyPagination(),
    permissionsPagination: emptyPagination(),
    groupsPagination: emptyPagination(),
    permissionsLoaded: false,
    groupsLoaded: false,
    loading: false,
    requestVersion: 0
  })
  const controller = state as UserAdministrationController
  Object.defineProperties(controller, {
    getUsers: { get: () => state.users },
    getPermissions: { get: () => state.permissions },
    getGroups: { get: () => state.groups },
    isLoading: { get: () => state.loading }
  })

  controller.clearList = () => {
    state.requestVersion++
    state.users = []
  }
  controller.fetchUsers = (query = {}) => fetchUsers(state, query)
  controller.updateUser = (id, data) => updateUser(state, id, data)
  controller.deleteUser = (id) => deleteUser(state, id)
  controller.fetchPermissions = (query = {}) => fetchPermissions(state, query)
  controller.fetchGroups = (query = {}) => fetchGroups(state, query)
  controller.saveGroup = async (id, name, permissionIds) => {
    await handleRequest<IGroup>(
      id === undefined
        ? apiClient.post(`${usersPath}/groups/`, { name, permission_ids: permissionIds })
        : apiClient.patch(`${usersPath}/groups/${id}/`, { name, permission_ids: permissionIds }),
      (group) => {
        state.groups = [...state.groups.filter((item) => item.id !== group.id), group].sort(
          (a, b) => String(a.name).localeCompare(String(b.name))
        )
        state.groupsPagination.count = state.groups.length
        notifySuccess('Role saved.')
      },
      notifyError
    )
  }
  controller.deleteGroup = async (id) => {
    await handleRequest(
      apiClient.delete(`${usersPath}/groups/${id}/`),
      () => {
        state.groups = state.groups.filter((group) => group.id !== id)
        state.groupsPagination.count = state.groups.length
        notifySuccess('Role deleted.')
      },
      notifyError
    )
  }
  return controller
}

export function provideUserAdministrationController(
  controller = createUserAdministrationController()
): UserAdministrationController {
  provide(controllerKey, controller)
  return controller
}

export function useUserAdministrationController(): UserAdministrationController {
  const controller = inject(controllerKey)
  if (!controller) throw new Error('User administration controller is outside its route boundary.')
  return controller
}

async function fetchUsers(state: UserAdministrationState, query: PaginationQuery): Promise<void> {
  const version = ++state.requestVersion
  state.loading = true
  try {
    const response = await handleRequest<IUser[]>(
      apiClient.get(`${usersPath}/`, { params: compactPaginationQuery(query) }),
      (data) => {
        if (version === state.requestVersion) state.users = data
      },
      (error) => {
        if (version === state.requestVersion) notifyError(error)
      }
    )
    if (version === state.requestVersion)
      state.usersPagination = getPaginationMeta<IUser>(response) || state.usersPagination
  } catch (error) {
    if (version === state.requestVersion) throw error
  } finally {
    if (version === state.requestVersion) state.loading = false
  }
}

async function updateUser(state: UserAdministrationState, id: number, data: IUser): Promise<void> {
  state.loading = true
  await handleRequest<IUser>(
    apiClient.patch(`${usersPath}/${id}/`, data),
    (updated) => {
      const index = state.users.findIndex((user) => user.id === id)
      if (index >= 0) state.users[index] = { ...state.users[index], ...updated }
      notifySuccess('Updated successfully.')
    },
    notifyError,
    () => (state.loading = false)
  )
}

async function deleteUser(state: UserAdministrationState, id: number): Promise<void> {
  state.loading = true
  await handleRequest<void>(
    apiClient.delete(`${usersPath}/${id}/`),
    () => {
      state.users = state.users.filter((user) => user.id !== id)
      state.usersPagination.count = Math.max(0, state.usersPagination.count - 1)
      notifySuccess('Deleted successfully.')
    },
    notifyError,
    () => (state.loading = false)
  )
}

/** Publish catalog data only after every page has loaded, so edits cannot drop unseen access. */
async function fetchCatalog<T>(path: string, query: PaginationQuery): Promise<T[]> {
  const items: T[] = []
  let page = 1
  let hasNext = true
  while (hasNext) {
    const response = await handleRequest<T[]>(
      apiClient.get(`${usersPath}/${path}/`, {
        params: { ...compactPaginationQuery(query), page, page_size: 200 }
      }),
      (data) => items.push(...data),
      notifyError
    )
    hasNext = Boolean(getPaginationMeta<T>(response)?.next)
    page += 1
  }
  return items
}

async function fetchPermissions(
  state: UserAdministrationState,
  query: PaginationQuery
): Promise<void> {
  state.permissionsLoaded = false
  state.permissions = await fetchCatalog<IPermission>('permissions', query)
  state.permissionsPagination = { count: state.permissions.length, next: null, previous: null }
  state.permissionsLoaded = true
}

async function fetchGroups(state: UserAdministrationState, query: PaginationQuery): Promise<void> {
  state.groupsLoaded = false
  state.groups = await fetchCatalog<IGroup>('groups', query)
  state.groupsPagination = { count: state.groups.length, next: null, previous: null }
  state.groupsLoaded = true
}

function emptyPagination(): PaginationMeta {
  return { count: 0, next: null, previous: null }
}
