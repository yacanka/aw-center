import axios from 'axios'
import type { AxiosError, GenericAbortSignal, InternalAxiosRequestConfig } from 'axios'
import { normalizeApiBaseUrl, normalizeApiRequestPath } from '@/shared/api/apiUrl'

export const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_URL)
const DEFAULT_TIMEOUT_MILLISECONDS = 10000
const API_TIMEOUT_MILLISECONDS = Number(
  import.meta.env.VITE_API_TIMEOUT_MS || DEFAULT_TIMEOUT_MILLISECONDS
)

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT_MILLISECONDS,
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken'
})

const UNSAFE_HTTP_METHODS = new Set(['post', 'put', 'patch', 'delete'])
let authenticationFailureHandler: (() => void) | null = null
let sessionRequestController = new AbortController()

/**
 * Ensures browser cookie-token requests include Django's CSRF header.
 */
apiClient.interceptors.request.use((config) => {
  config.url = normalizeApiRequestPath(config.url || '')
  config.withCredentials = true
  config.signal = combineAbortSignals(config.signal, sessionRequestController.signal)
  attachCsrfToken(config)
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (isAuthenticationFailure(error)) authenticationFailureHandler?.()
    return Promise.reject(error)
  }
)

/** Distinguish an expired session from an ordinary permission-denied response. */
export function isAuthenticationFailure(error: Pick<AxiosError, 'response'>): boolean {
  if (error.response?.status === 401) return true
  if (error.response?.status !== 403) return false
  const payload = error.response.data
  return isRecord(payload) && payload.code === 'NOT_AUTHENTICATED'
}

function attachCsrfToken(config: InternalAxiosRequestConfig) {
  const method = config.method?.toLowerCase()
  const csrfToken = readCookie('csrftoken')

  if (!method || !UNSAFE_HTTP_METHODS.has(method) || !csrfToken) {
    return
  }

  config.headers.set('X-CSRFToken', csrfToken)
}

function readCookie(name: string) {
  if (typeof document === 'undefined') return null
  const cookies = document.cookie ? document.cookie.split('; ') : []
  const cookie = cookies.find((item) => item.startsWith(`${name}=`))
  return cookie ? decodeURIComponent(cookie.split('=').slice(1).join('=')) : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Object.prototype.toString.call(value) === '[object Object]'
}

/** Keep reactive session state synchronized with server-side cookie invalidation. */
export function registerAuthenticationFailureHandler(handler: () => void): () => void {
  authenticationFailureHandler = handler
  return () => {
    if (authenticationFailureHandler === handler) authenticationFailureHandler = null
  }
}

/** Cancel requests owned by the previous anonymous/authenticated browser session. */
export function cancelSessionScopedRequests(): void {
  sessionRequestController.abort()
  sessionRequestController = new AbortController()
}

function combineAbortSignals(
  requestSignal: GenericAbortSignal | undefined,
  sessionSignal: AbortSignal
): GenericAbortSignal {
  if (!requestSignal) return sessionSignal
  const addEventListener = requestSignal.addEventListener?.bind(requestSignal)
  const removeEventListener = requestSignal.removeEventListener?.bind(requestSignal)
  if (!addEventListener || !removeEventListener) return sessionSignal

  const controller = new AbortController()
  const abort = () => {
    removeEventListener('abort', abort)
    sessionSignal.removeEventListener('abort', abort)
    controller.abort()
  }
  if (requestSignal.aborted || sessionSignal.aborted) abort()
  else {
    addEventListener('abort', abort, { once: true })
    sessionSignal.addEventListener('abort', abort, { once: true })
  }
  return controller.signal
}
