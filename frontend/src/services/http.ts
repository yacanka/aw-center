import axios from 'axios'
import type { InternalAxiosRequestConfig } from 'axios'
import { readString, STORAGE_KEYS } from '@/services/storage'

export const API_BASE_URL = import.meta.env.VITE_API_URL || ''
const DEFAULT_TIMEOUT_MILLISECONDS = 10000
const API_TIMEOUT_MILLISECONDS = Number(
  import.meta.env.VITE_API_TIMEOUT_MS || DEFAULT_TIMEOUT_MILLISECONDS
)

axios.defaults.baseURL = API_BASE_URL
axios.defaults.timeout = API_TIMEOUT_MILLISECONDS
axios.defaults.withCredentials = true
axios.defaults.xsrfCookieName = 'csrftoken'
axios.defaults.xsrfHeaderName = 'X-CSRFToken'

const UNSAFE_HTTP_METHODS = new Set(['post', 'put', 'patch', 'delete'])

/**
 * Ensures browser cookie-token requests include Django's CSRF header.
 */
axios.interceptors.request.use((config) => {
  config.withCredentials = true
  attachCsrfToken(config)
  return config
})

function attachCsrfToken(config: InternalAxiosRequestConfig) {
  const method = config.method?.toLowerCase()
  const csrfToken = readCookie('csrftoken')

  if (!method || !UNSAFE_HTTP_METHODS.has(method) || !csrfToken) {
    return
  }

  config.headers.set('X-CSRFToken', csrfToken)
}

function readCookie(name: string) {
  const cookies = document.cookie ? document.cookie.split('; ') : []
  const cookie = cookies.find((item) => item.startsWith(`${name}=`))
  return cookie ? decodeURIComponent(cookie.split('=').slice(1).join('=')) : null
}

/**
 * Sets or clears the shared Axios token header for authenticated API calls.
 */
export function setAuthToken(token: string | null) {
  if (token) {
    axios.defaults.headers.common['Authorization'] = `Token ${token}`
    return
  }

  delete axios.defaults.headers.common['Authorization']
}

/**
 * Restores the optional development token fallback for cross-origin HTTP setups.
 */
export function bootstrapHttpAuth() {
  setAuthToken(readString(STORAGE_KEYS.token))
}
