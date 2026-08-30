import { apiClient, isAuthenticationFailure } from '@/shared/api/http'
import { isAxiosError } from 'axios'
import type { IPreferences, IUser } from '@/features/session/models/auth'

export interface LoginCredentials {
  username: string
  password: string
}

export interface SessionResponse {
  state: 'authenticated' | 'anonymous'
  user: IUser | null
}

/** Resolve the current HttpOnly-cookie session. */
export async function fetchSession(): Promise<SessionResponse> {
  return hydratePreferences(
    normalizeSessionResponse((await apiClient.get<unknown>('session/')).data)
  )
}

/** Create a new HttpOnly-cookie session. */
export async function createSession(credentials: LoginCredentials): Promise<SessionResponse> {
  return hydratePreferences(
    normalizeSessionResponse((await apiClient.post<unknown>('session/', credentials)).data)
  )
}

/** Revoke the current HttpOnly-cookie session. */
export async function deleteSession(): Promise<void> {
  await apiClient.delete('session/')
}

/** Update current-user preferences without persisting session identity in the browser. */
export async function updateSessionPreferences(payload: IPreferences): Promise<IPreferences> {
  return (await apiClient.patch<IPreferences>('users/preferences/', payload)).data
}

export async function requestPasswordReset(payload: object): Promise<void> {
  await apiClient.post('users/password-reset/', payload)
}

export async function confirmPasswordReset(payload: object): Promise<void> {
  await apiClient.post('users/password-reset/confirm/', payload)
}

export async function changeSessionPassword(payload: object): Promise<void> {
  await apiClient.post('users/password/', payload)
}

function normalizeSessionResponse(data: unknown): SessionResponse {
  if (!isRecord(data) || !['authenticated', 'anonymous'].includes(String(data.state))) {
    throw new Error('The session response is invalid.')
  }

  if (data.state === 'anonymous') {
    if (data.user !== null) throw new Error('The anonymous session response is invalid.')
    return { state: 'anonymous', user: null }
  }

  if (!isRecord(data.user) || typeof data.user.id !== 'number') {
    throw new Error('The authenticated session response is invalid.')
  }

  return {
    state: 'authenticated',
    user: {
      ...data.user,
      permissions: normalizePermissions(data.user.permissions)
    }
  }
}

async function hydratePreferences(response: SessionResponse): Promise<SessionResponse> {
  if (!response.user) return response
  try {
    response.user.preferences = (await apiClient.get<IPreferences>('users/preferences/')).data
  } catch (error) {
    if (isAxiosError(error) && isAuthenticationFailure(error)) throw error
    response.user.preferences = {}
  }
  return response
}

function normalizePermissions(value: unknown) {
  if (!Array.isArray(value)) return []
  return value.flatMap((permission) => {
    if (isRecord(permission)) return [permission]
    if (typeof permission !== 'string') return []
    const separator = permission.indexOf('.')
    if (separator <= 0) return []
    return [
      {
        codename: permission.slice(separator + 1),
        content_type: { app_label: permission.slice(0, separator) }
      }
    ]
  })
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Object.prototype.toString.call(value) === '[object Object]'
}
