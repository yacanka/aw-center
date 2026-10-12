import axios from 'axios'
import type {
  AxiosError,
  AxiosRequestTransformer,
  GenericAbortSignal,
  InternalAxiosRequestConfig
} from 'axios'
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
const abortCleanups = new WeakMap<InternalAxiosRequestConfig, () => void>()

/**
 * Ensures browser cookie-token requests include Django's CSRF header.
 */
apiClient.interceptors.request.use((config) => {
  config.url = normalizeApiRequestPath(config.url || '')
  config.withCredentials = true
  attachCsrfToken(config)
  const combined = combineAbortSignals(config.signal, sessionRequestController.signal)
  config.signal = combined.signal
  if (combined.cleanup) {
    abortCleanups.set(config, combined.cleanup)
    cleanupRequestOnCompletion(config)
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => {
    cleanupAbortListeners(response.config)
    return response
  },
  (error: AxiosError) => {
    cleanupAbortListeners(error.config)
    if (isAuthenticationFailure(error)) authenticationFailureHandler?.()
    return Promise.reject(error)
  }
)

function cleanupAbortListeners(config: InternalAxiosRequestConfig | undefined): void {
  if (!config) return
  abortCleanups.get(config)?.()
  abortCleanups.delete(config)
}

function cleanupRequestOnCompletion(config: InternalAxiosRequestConfig): void {
  // Axios may reject serialization or an adapter with an error that has no request config.
  const transforms: AxiosRequestTransformer[] = config.transformRequest
    ? Array.isArray(config.transformRequest)
      ? config.transformRequest
      : [config.transformRequest]
    : []
  config.transformRequest = transforms.map(
    (transform) =>
      function (data, headers) {
        try {
          return transform.call(this, data, headers)
        } catch (error) {
          cleanupAbortListeners(this)
          throw error
        }
      }
  )
  const adapter = config.adapter
  if (typeof adapter !== 'function') return
  config.adapter = async (requestConfig) => {
    try {
      return await adapter(requestConfig)
    } finally {
      cleanupAbortListeners(requestConfig)
    }
  }
}

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
): { signal: GenericAbortSignal; cleanup?: () => void } {
  if (!requestSignal) return { signal: sessionSignal }
  const addEventListener = requestSignal.addEventListener?.bind(requestSignal)
  const removeEventListener = requestSignal.removeEventListener?.bind(requestSignal)
  if (!addEventListener || !removeEventListener) return { signal: sessionSignal }

  const controller = new AbortController()
  const cleanup = () => {
    removeEventListener('abort', abort)
    sessionSignal.removeEventListener('abort', abort)
  }
  const abort = () => {
    cleanup()
    controller.abort()
  }
  if (requestSignal.aborted || sessionSignal.aborted) abort()
  else {
    addEventListener('abort', abort, { once: true })
    sessionSignal.addEventListener('abort', abort, { once: true })
  }
  return { signal: controller.signal, cleanup }
}
