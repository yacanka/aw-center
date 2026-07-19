import { IUser, IPermission, IPreferences } from '@/models/auth'
import { defineStore } from 'pinia'
import axios from 'axios'
import { handleRequest } from '@/composables/promise'
import { setAuthToken } from '@/services/http'
import { notifyError } from '@/services/notify'
import { readJson, STORAGE_KEYS, removeKey, writeJson, writeString } from '@/services/storage'
import { hasEffectivePermission } from '@/services/accessPolicy'

type CurrentUserOptions = {
  allowCachedFallback?: boolean
  suppressAuthenticationWarning?: boolean
}

export function setUser(user: IUser) {
  writeJson(STORAGE_KEYS.user, user)
}

export function getUser() {
  return readJson<IUser | null>(STORAGE_KEYS.user, null)
}

export function isAuthenticated() {
  return !!getUser()
}

export function logout() {
  removeKey(STORAGE_KEYS.token)
  removeKey(STORAGE_KEYS.user)
  removeKey(STORAGE_KEYS.project)
  setAuthToken(null)
}

export function setProjectName(name: string) {
  writeString(STORAGE_KEYS.project, name)
}

export const useUserStore = defineStore('user', {
  state: () => ({
    loading: true,
    sessionInitialized: false,
    user: {} as IUser,
    permissions: [] as IPermission[],
    preferences: {} as IPreferences
  }),
  getters: {
    getUser: (state) => state.user,
    isSessionInitialized: (state) => state.sessionInitialized,
    getPermissions: (state) => state.permissions,
    getPreferences: (state) => state.preferences
  },
  actions: {
    setUser(user: IUser) {
      this.user = user
      this.permissions = user.permissions || []
      this.preferences = user.preferences || {}
      setUser(user)
    },
    setSessionInitialized() {
      this.sessionInitialized = true
    },
    checkPermission(permissionName: string) {
      return this.permissions.some((permission) => permission.codename == permissionName)
    },
    hasRole(app: string, role: string) {
      return this.permissions.some(
        (permission: IPermission) =>
          permission.content_type?.app_label == app && permission.codename == role
      )
    },
    hasEffectiveRole(app: string, role: string) {
      return hasEffectivePermission(this.user, `${app}.${role}`)
    },
    async updatePreference(preferencesData: IPreferences) {
      this.loading = true
      await handleRequest<IPreferences>(
        axios.patch(`auth/preferences/`, preferencesData), // POST request
        (data) => {
          this.preferences = data // Add created doc to existing list
          window.$message.success('Preferences updated successfully.')
        },
        (errorMsg) => {
          notifyError(errorMsg)
          console.log(errorMsg)
        },
        () => (this.loading = false)
      )
    },
    async fetchCurrentUser(options: CurrentUserOptions = {}) {
      this.loading = true
      let isLoaded = false
      let requestError: Error | null = null
      await handleRequest<IUser>(
        axios.get(`auth/me/`),
        (data) => {
          this.setUser(data)
          isLoaded = true
        },
        () => {
          isLoaded = this.restoreCachedUser(options)
        },
        () => (this.loading = false),
        { suppressAuthenticationWarning: options.suppressAuthenticationWarning }
      ).catch((error) => (requestError = error))
      if (!isLoaded && requestError && !options.allowCachedFallback) throw requestError
      return isLoaded
    },
    restoreCachedUser(options: CurrentUserOptions) {
      const cachedUser = getUser()
      if (!options.allowCachedFallback || !cachedUser) return false

      this.setUser(cachedUser)
      return true
    },
    async resetPasswordRequest(payload: object) {
      this.loading = true
      await handleRequest<IUser>(
        axios.post(`auth/password-reset/`, payload),
        (data) => {
          console.log(data)
        },
        (errorMsg) => {
          console.log(errorMsg)
        },
        () => (this.loading = false)
      )
    },
    async resetPasswordConfirm(payload: object) {
      this.loading = true
      await handleRequest<IUser>(
        axios.post(`auth/password-reset/confirm/`, payload),
        (data) => {
          console.log(data)
        },
        (errorMsg) => {
          console.log(errorMsg)
        },
        () => (this.loading = false)
      )
    }
  }
})
