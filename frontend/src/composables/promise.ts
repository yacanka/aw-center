import type { AxiosError, AxiosResponse } from 'axios'
import { formatApiError } from '@/services/apiError'
import { setAuthToken } from '@/services/http'
import { notifyWarning } from '@/services/notify'
import { removeKey, STORAGE_KEYS } from '@/services/storage'
import { isPaginatedResponse } from '@/services/pagination'

type ErrorPayload = Record<string, unknown> | string | null | undefined

type RequestOptions = {
  suppressAuthenticationWarning?: boolean
}

export class RequestError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly code?: string,
    readonly errors?: unknown
  ) {
    super(message)
    this.name = 'RequestError'
  }
}

function clearStoredAuthentication() {
  removeKey(STORAGE_KEYS.token)
  removeKey(STORAGE_KEYS.user)
  removeKey(STORAGE_KEYS.project)
  removeKey(STORAGE_KEYS.jiraSession)
  setAuthToken(null)
}

function isAuthenticationFailure(error: AxiosError<ErrorPayload>) {
  return error.response?.status === 401
}

function handleAuthenticationFailure(error: AxiosError<ErrorPayload>, options: RequestOptions) {
  if (!isAuthenticationFailure(error)) return
  clearStoredAuthentication()
  if (options.suppressAuthenticationWarning) return
  notifyWarning('Login required.', 'Authentication Required')
}

function handleSuccessfulResponse<T>(response: AxiosResponse<T>) {
  if ([200, 201, 204].includes(response.status)) return response.data

  throw new Error(`Request failed with status: ${response.status}`)
}

/**
 * Executes an HTTP request with shared response parsing, auth cleanup, and error formatting.
 */
export async function handleRequest<T>(
  request: Promise<AxiosResponse<T>>,
  onSuccess: (data: T) => void,
  onError: (errorMsg: string) => void,
  onFinally?: () => void,
  options: RequestOptions = {}
) {
  try {
    const data = handleSuccessfulResponse(await request)
    const successData = isPaginatedResponse(data)
      ? data.results
      : (data as { message?: T })?.message || data
    onSuccess(successData as T)
    return data
  } catch (error) {
    const axiosError = error as AxiosError<ErrorPayload>
    const errorMessage = formatApiError(axiosError.response?.data)
    const isAuthFailure = isAuthenticationFailure(axiosError)
    handleAuthenticationFailure(axiosError, options)
    if (!isAuthFailure || options.suppressAuthenticationWarning) onError(errorMessage)
    const payload =
      axiosError.response?.data && typeof axiosError.response.data === 'object'
        ? axiosError.response.data
        : {}
    throw new RequestError(
      errorMessage,
      axiosError.response?.status,
      typeof payload.code === 'string' ? payload.code : undefined,
      payload.errors
    )
  } finally {
    onFinally?.()
  }
}
