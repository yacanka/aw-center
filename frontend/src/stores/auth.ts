import { defineStore } from 'pinia'
import axios from 'axios'
import { IUser, IPermission, IGroup } from '@/models/auth'
import { handleRequest } from '@/composables/promise'
import { setAuthToken } from '@/services/http'
import { notifyError, notifySuccess } from '@/services/notify'
import { removeKey, STORAGE_KEYS, writeString } from '@/services/storage'
import {
  compactPaginationQuery,
  getPaginationMeta,
  PaginationMeta,
  PaginationQuery
} from '@/services/pagination'

const API_PATH = 'auth'

type LoginResponse = {
  detail: string
  user: IUser
  token?: string
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    me: {} as IUser,
    token: '' as string,
    users: [] as IUser[],
    permissions: [] as IPermission[],
    groups: [] as IGroup[],
    usersPagination: { count: 0, next: null, previous: null } as PaginationMeta,
    permissionsPagination: { count: 0, next: null, previous: null } as PaginationMeta,
    groupsPagination: { count: 0, next: null, previous: null } as PaginationMeta,
    loading: false,
    ipAddress: axios.defaults.baseURL
  }),
  getters: {
    getMe: (state) => state.me,
    getUsers: (state) => state.users,
    getToken: (state) => state.token,
    getPermissions: (state) => state.permissions,
    getGroups: (state) => state.groups,
    isLoading: (state) => state.loading
  },
  actions: {
    clearList() {
      this.users = []
    },
    async login(credentials: any) {
      this.loading = true
      let authenticatedUser: IUser | null = null
      setAuthToken(null)
      removeKey(STORAGE_KEYS.token)
      await handleRequest<LoginResponse>(
        axios.post(`${API_PATH}/token/`, credentials),
        (data) => {
          this.me = data.user
          this.token = data.token || 'cookie-auth'
          applyOptionalTokenFallback(data.token)
          authenticatedUser = data.user
          notifySuccess(data.detail || 'Login successful')
        },
        (errorMessage) => {
          notifyError(errorMessage)
        },
        () => {
          this.loading = false
        }
      ).catch(() => undefined)
      return authenticatedUser
    },
    async fetchUsers(query: PaginationQuery = {}) {
      this.loading = true
      const response = await handleRequest<IUser[]>(
        axios.get(`${API_PATH}/users/`, { params: compactPaginationQuery(query) }),
        (data) => {
          this.users = data
        },
        (errorMsg) => {
          notifyError(errorMsg)
          console.log(errorMsg)
        },
        () => {
          this.loading = false
        }
      )
      this.usersPagination = getPaginationMeta<IUser>(response) || this.usersPagination
    },
    async updateUser(userId: Number, updatedData: IUser) {
      this.loading = true
      await handleRequest<any>(
        axios.patch(`${API_PATH}/users/${userId}/`, updatedData),
        (data) => {
          const existingIndex = this.users.findIndex((user) => user.id === userId)
          if (existingIndex !== -1) {
            this.users[existingIndex] = { ...this.users[existingIndex], ...data }
          }
          notifySuccess('Updated successfully.')
        },
        (errorMsg) => {
          notifyError(errorMsg)
          console.log(errorMsg)
        },
        () => {
          this.loading = false
        }
      )
    },
    async deleteUser(userId: Number) {
      this.loading = true
      await handleRequest<void>(
        axios.delete(`${API_PATH}/users/${userId}/`),
        () => {
          this.users = this.users.filter((user: IUser) => user.id !== userId)
          notifySuccess('Deleted successfully.')
        },
        (errorMsg) => {
          notifyError(errorMsg)
          console.log(errorMsg)
        },
        () => {
          this.loading = false
        }
      )
    },
    async signup(credentials: any) {
      this.loading = true
      await handleRequest<any>(
        axios.post(`${API_PATH}/signup/`, credentials),
        () => {
          notifySuccess('Registration successful')
        },
        (errorMsg) => {
          notifyError(errorMsg)
          console.log(errorMsg)
        },
        () => {
          this.loading = false
        }
      )
    },
    async logout() {
      this.loading = true
      await handleRequest<any>(
        axios.post(`${API_PATH}/logout/`),
        () => undefined,
        () => undefined,
        () => {
          this.loading = false
        },
        { suppressAuthenticationWarning: true }
      ).catch(() => undefined)

      this.me = {} as IUser
      this.token = ''
      setAuthToken(null)
      removeKey(STORAGE_KEYS.token)
      removeKey(STORAGE_KEYS.user)
      removeKey(STORAGE_KEYS.project)
      notifySuccess('Logout successful')
    },
    async fetchPermissions(query: PaginationQuery = {}) {
      this.loading = true
      const response = await handleRequest<IPermission[]>(
        axios.get(`${API_PATH}/permissions/`, { params: compactPaginationQuery(query) }),
        (data) => {
          this.permissions = data
        },
        (errorMsg) => {
          console.log(errorMsg)
        },
        () => {
          this.loading = false
        }
      )
      this.permissionsPagination =
        getPaginationMeta<IPermission>(response) || this.permissionsPagination
    },
    async fetchGroups(query: PaginationQuery = {}) {
      this.loading = true
      const response = await handleRequest<IGroup[]>(
        axios.get(`${API_PATH}/groups/`, { params: compactPaginationQuery(query) }),
        (data) => {
          this.groups = data
        },
        (errorMsg) => {
          notifyError(errorMsg)
        },
        () => {
          this.loading = false
        }
      )
      this.groupsPagination = getPaginationMeta<IGroup>(response) || this.groupsPagination
    },
    async changePassword(password: any) {
      this.loading = true
      await handleRequest<any>(
        axios.post(`${API_PATH}/change_password/`, password),
        (data) => {
          notifySuccess(data)
        },
        (errorMsg) => {
          notifyError(errorMsg)
        },
        () => {
          this.loading = false
        }
      )
    }
  }
})

function applyOptionalTokenFallback(token?: string) {
  if (!token) return

  setAuthToken(token)
  writeString(STORAGE_KEYS.token, token)
}
