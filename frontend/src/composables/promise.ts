import type { AxiosError, AxiosResponse } from 'axios'
import { formatApiError } from '@/services/apiError'
import { setAuthToken } from '@/services/http'
import { notifyWarning } from '@/services/notify'
import { removeKey, STORAGE_KEYS } from '@/services/storage'
import { isPaginatedResponse } from '@/services/pagination'

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

function handleAuthenticationFailure(error: AxiosError<ErrorPayload>) {
  if (!isAuthenticationFailure(error)) return

  clearStoredAuthentication()
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
  onFinally?: () => void
) {
  try {
    const data = handleSuccessfulResponse(await request)
    const successData = isPaginatedResponse(data) ? data.results : (data as { message?: T })?.message || data
    onSuccess(successData as T)
    return data
  } catch (error) {
    const axiosError = error as AxiosError<ErrorPayload>
    const errorMessage = formatApiError(axiosError.response?.data)
    handleAuthenticationFailure(axiosError)
    onError(errorMessage)
    throw new Error(errorMessage)
  } finally {
    onFinally?.()
  }
}
