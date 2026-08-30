import type { AxiosError, AxiosResponse } from 'axios'
import { formatApiError } from '@/shared/api/apiError'
import { notifyWarning } from '@/shared/services/notify'
import { isPaginatedResponse } from '@/shared/services/pagination'
import { isAuthenticationFailure } from '@/shared/api/http'

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

function handleAuthenticationFailure(error: AxiosError<ErrorPayload>, options: RequestOptions) {
  if (!isAuthenticationFailure(error)) return
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
    if (axiosError.code === 'ERR_CANCELED') {
      throw new RequestError('Request cancelled.', undefined, 'REQUEST_CANCELLED')
    }
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
