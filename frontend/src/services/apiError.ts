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
 * Formats standard and legacy API errors into a user-facing message.
 */
export function formatApiError(data: unknown): string {
  const responseData = getResponseData(data)
  if (responseData !== undefined) return formatApiError(responseData)
  if (isApiErrorPayload(data)) return formatStandardError(data)
  if (isRecord(data)) return formatLegacyObjectError(data)
  if (typeof data === 'string' && isJsonString(data)) return parseJsonError(data)
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

function formatLegacyObjectError(data: Record<string, unknown>): string {
  if (typeof data.detail === 'string') return data.detail
  if (typeof data.message === 'string') return data.message
  if (typeof data.error === 'string') return data.error
  return stringifyObjectErrors(data)
}

function isRecord(data: unknown): data is Record<string, unknown> {
  return Object.prototype.toString.call(data) === '[object Object]'
}

function isObjectLike(data: unknown): data is object {
  return typeof data === 'object' && data !== null
}

function parseJsonError(data: string): string {
  const parsed = JSON.parse(data) as { errors?: Record<string, unknown> }
  return stringifyObjectErrors(parsed.errors ?? {}) || FALLBACK_ERROR_MESSAGE
}

function stringifyObjectErrors(data: Record<string, unknown>): string {
  return Object.entries(data)
    .map(([key, value]) => `${key}: ${stringifyErrorValue(value)}`)
    .join('\n')
}

function stringifyErrorValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ')
  if (isRecord(value)) return stringifyObjectErrors(value)
  return String(value)
}

function isJsonString(value: string): boolean {
  try {
    JSON.parse(value)
    return value.trim().length > 0
  } catch {
    return false
  }
}
