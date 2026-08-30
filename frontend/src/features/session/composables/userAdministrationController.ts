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
  loading: boolean
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
    loading: false
  })
  const controller = state as UserAdministrationController
  Object.defineProperties(controller, {
    getUsers: { get: () => state.users },
    getPermissions: { get: () => state.permissions },
    getGroups: { get: () => state.groups },
    isLoading: { get: () => state.loading }
  })

  controller.clearList = () => (state.users = [])
  controller.fetchUsers = (query = {}) => fetchUsers(state, query)
  controller.updateUser = (id, data) => updateUser(state, id, data)
  controller.deleteUser = (id) => deleteUser(state, id)
  controller.fetchPermissions = (query = {}) => fetchPermissions(state, query)
  controller.fetchGroups = (query = {}) => fetchGroups(state, query)
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
  state.loading = true
  const response = await handleRequest<IUser[]>(
    apiClient.get(`${usersPath}/`, { params: compactPaginationQuery(query) }),
    (data) => (state.users = data),
    notifyError,
    () => (state.loading = false)
  )
  state.usersPagination = getPaginationMeta<IUser>(response) || state.usersPagination
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
      notifySuccess('Deleted successfully.')
    },
    notifyError,
    () => (state.loading = false)
  )
}

async function fetchPermissions(
  state: UserAdministrationState,
  query: PaginationQuery
): Promise<void> {
  state.loading = true
  const response = await handleRequest<IPermission[]>(
    apiClient.get(`${usersPath}/permissions/`, { params: compactPaginationQuery(query) }),
    (data) => (state.permissions = data),
    notifyError,
    () => (state.loading = false)
  )
  state.permissionsPagination =
    getPaginationMeta<IPermission>(response) || state.permissionsPagination
}

async function fetchGroups(state: UserAdministrationState, query: PaginationQuery): Promise<void> {
  state.loading = true
  const response = await handleRequest<IGroup[]>(
    apiClient.get(`${usersPath}/groups/`, { params: compactPaginationQuery(query) }),
    (data) => (state.groups = data),
    notifyError,
    () => (state.loading = false)
  )
  state.groupsPagination = getPaginationMeta<IGroup>(response) || state.groupsPagination
}

function emptyPagination(): PaginationMeta {
  return { count: 0, next: null, previous: null }
}
