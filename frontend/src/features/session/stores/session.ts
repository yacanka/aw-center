import { defineStore } from 'pinia'
import { isAxiosError } from 'axios'
import type { IPermission, IPreferences, IUser } from '@/features/session/models/auth'
import { hasEffectivePermission } from '@/features/session/services/accessPolicy'
import { formatApiError } from '@/shared/api/apiError'
import { notifyError, notifySuccess } from '@/shared/services/notify'
import {
  changeSessionPassword,
  confirmPasswordReset,
  createSession,
  deleteSession,
  fetchSession,
  requestPasswordReset,
  updateSessionPreferences,
  type LoginCredentials
} from '@/features/session/api/sessionApi'
import { resetSessionScopedStores } from '@/features/session/stores/sessionScope'
import { cancelSessionScopedRequests, isAuthenticationFailure } from '@/shared/api/http'

export type SessionStatus = 'unknown' | 'authenticated' | 'anonymous' | 'unavailable'

export const useSessionStore = defineStore('session', {
  state: () => ({
    status: 'unknown' as SessionStatus,
    user: null as IUser | null,
    loading: false
  }),
  getters: {
    getUser: (state): IUser => state.user || {},
    getPermissions: (state): IPermission[] => state.user?.permissions || [],
    getPreferences: (state): IPreferences => state.user?.preferences || {},
    isAuthenticated: (state): boolean =>
      state.status === 'authenticated' && Boolean(state.user?.id),
    isSessionInitialized: (state): boolean => state.status !== 'unknown'
  },
  actions: {
    setAuthenticatedUser(user: IUser): void {
      if (this.status !== 'authenticated' || this.user?.id !== user.id) clearSessionScope()
      this.user = user
      this.status = 'authenticated'
    },
    markAnonymous(): void {
      clearSessionScope()
      this.user = null
      this.status = 'anonymous'
    },
    checkPermission(permissionName: string): boolean {
      return this.getPermissions.some((permission) => permission.codename === permissionName)
    },
    hasRole(app: string, role: string): boolean {
      return this.getPermissions.some(
        (permission) => permission.content_type?.app_label === app && permission.codename === role
      )
    },
    hasEffectiveRole(app: string, role: string): boolean {
      return hasEffectivePermission(this.getUser, `${app}.${role}`)
    },
    async bootstrap(force = false): Promise<SessionStatus> {
      if (!force && this.status !== 'unknown') return this.status

      this.loading = true
      try {
        const response = await fetchSession()
        if (response.state === 'authenticated' && response.user) {
          this.setAuthenticatedUser(response.user)
        } else {
          this.markAnonymous()
        }
      } catch (error) {
        clearSessionScope()
        this.user = null
        this.status =
          isAxiosError(error) && isAuthenticationFailure(error) ? 'anonymous' : 'unavailable'
      } finally {
        this.loading = false
      }
      return this.status
    },
    async login(credentials: LoginCredentials): Promise<IUser | null> {
      this.loading = true
      try {
        const response = await createSession(credentials)
        if (response.state !== 'authenticated' || !response.user) {
          throw new Error('The server did not establish an authenticated session.')
        }
        this.setAuthenticatedUser(response.user)
        notifySuccess('Login successful')
        return response.user
      } catch (error) {
        this.markAnonymous()
        notifyError(formatApiError(error))
        return null
      } finally {
        this.loading = false
      }
    },
    async logout(): Promise<void> {
      this.loading = true
      try {
        await deleteSession()
      } catch (error) {
        notifyError(formatApiError(error))
        throw error
      } finally {
        this.loading = false
      }

      this.markAnonymous()
      notifySuccess('Logout successful')
    },
    async updatePreference(preferences: IPreferences): Promise<void> {
      this.loading = true
      try {
        const updated = await updateSessionPreferences(preferences)
        if (this.user) this.user.preferences = updated
        notifySuccess('Preferences updated successfully.')
      } catch (error) {
        notifyError(formatApiError(error))
        throw error
      } finally {
        this.loading = false
      }
    },
    resetPasswordRequest(payload: object): Promise<void> {
      return requestPasswordReset(payload)
    },
    resetPasswordConfirm(payload: object): Promise<void> {
      return confirmPasswordReset(payload)
    },
    changePassword(payload: object): Promise<void> {
      return changeSessionPassword(payload)
    }
  }
})

function clearSessionScope(): void {
  cancelSessionScopedRequests()
  resetSessionScopedStores()
}
