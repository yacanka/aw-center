export const FALLBACK_ERROR_MESSAGE = 'Something went wrong.'

export type ApiErrorPayload = {
  detail: string
  code: string
  errors?: Record<string, unknown>
  retryable?: boolean
  recovery_hint?: string
  request_id?: string
}

/**
 * Returns true when a payload follows the shared AW Center API error contract.
 */
export function isApiErrorPayload(data: unknown): data is ApiErrorPayload {
  if (!isRecord(data)) return false
  if (typeof data.detail !== 'string' || typeof data.code !== 'string') return false
  if (data.retryable !== undefined && typeof data.retryable !== 'boolean') return false
  return data.recovery_hint === undefined || typeof data.recovery_hint === 'string'
}

/**
 * Formats canonical API errors and transport failures into a user-facing message.
 */
export function formatApiError(data: unknown): string {
  const responseData = getResponseData(data)
  if (responseData !== undefined) return formatApiError(responseData)
  if (isApiErrorPayload(data)) return formatStandardError(data)
  if (data instanceof Error && data.message) return data.message

  return typeof data === 'string' && data ? data : FALLBACK_ERROR_MESSAGE
}

/** Returns the stable API error code from either a payload or an HTTP client error. */
export function getApiErrorCode(data: unknown): string | undefined {
  const responseData = getResponseData(data)
  if (responseData !== undefined) return getApiErrorCode(responseData)
  return isApiErrorPayload(data) ? data.code : undefined
}

function formatStandardError(data: ApiErrorPayload): string {
  const lines = [data.detail]
  if (data.recovery_hint) lines.push(`Next step: ${data.recovery_hint}`)
  if (data.request_id) lines.push(`Reference: ${data.request_id}`)
  return lines.join('\n')
}

function getResponseData(data: unknown): unknown {
  if (!isObjectLike(data)) return undefined
  const response = Reflect.get(data, 'response')
  if (!isObjectLike(response)) return undefined
  return Reflect.get(response, 'data')
}

function isRecord(data: unknown): data is Record<string, unknown> {
  return Object.prototype.toString.call(data) === '[object Object]'
}

function isObjectLike(data: unknown): data is object {
  return typeof data === 'object' && data !== null
}
