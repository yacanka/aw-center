import type { AxiosError, AxiosResponse } from 'axios'
import { setAuthToken } from '@/services/http'
import { notifyWarning } from '@/services/notify'
import { removeKey, STORAGE_KEYS } from '@/services/storage'
import { isPlainObject } from '@/utils/general'
import { isJsonString } from '@/utils/text'

type ErrorPayload = Record<string, unknown> | string | null | undefined

function clearStoredAuthentication() {
  removeKey(STORAGE_KEYS.token)
  removeKey(STORAGE_KEYS.user)
  removeKey(STORAGE_KEYS.project)
  setAuthToken(null)
}

function isAuthenticationFailure(error: AxiosError<ErrorPayload>) {
  return error.response?.status === 401
}

function stringifyObjectErrors(data: Record<string, unknown>) {
  return Object.entries(data)
    .map(([key, value]) => `${key}: ${value}`)
    .join('\n')
}

function parseJsonError(data: string) {
  const parsed = JSON.parse(data) as { errors?: Record<string, unknown> }
  return stringifyObjectErrors(parsed.errors ?? {})
}

function formatErrorPayload(data: ErrorPayload) {
  if (isPlainObject(data)) {
    return formatPlainObjectError(data)
  }

  if (typeof data === 'string' && isJsonString(data)) {
    return parseJsonError(data)
  }

  return typeof data === 'string' && data ? data : 'Something went wrong.'
}

function formatPlainObjectError(data: Record<string, unknown>) {
  if (typeof data.detail === 'string') return data.detail
  if (typeof data.message === 'string') return data.message
  if (typeof data.error === 'string') return data.error
  return stringifyObjectErrors(data)
}

function handleAuthenticationFailure(error: AxiosError<ErrorPayload>) {
  if (!isAuthenticationFailure(error)) return

  clearStoredAuthentication()
  notifyWarning('Login required.', 'Authentication Required')
}

function handleSuccessfulResponse<T>(response: AxiosResponse<T>) {
  if ([200, 201, 204].includes(response.status)) {
    return response.data
  }

  throw new Error(`Request failed with status: ${response.status}`)
}

/**
 * Executes an HTTP request with shared response parsing, auth cleanup, and error formatting.
 */
export async function handleRequest<T>(
  request: Promise<AxiosResponse<T>>,
  onSuccess: (data: T) => void,
  onError: (errorMsg: string) => void,
  onFinally?: () => void
) {
  try {
    const data = handleSuccessfulResponse(await request)
    onSuccess((data as { message?: T })?.message || data)
    return data
  } catch (error) {
    const axiosError = error as AxiosError<ErrorPayload>
    const errorMessage = formatErrorPayload(axiosError.response?.data)
    handleAuthenticationFailure(axiosError)
    onError(errorMessage)
    throw new Error(errorMessage)
  } finally {
    onFinally?.()
  }
}
