import { isJsonString } from '@/utils/text'

export const FALLBACK_ERROR_MESSAGE = 'Something went wrong.'

export type ApiErrorPayload = {
  detail: string
  code: string
  errors?: Record<string, unknown>
}

/**
 * Returns true when a payload follows the shared AW Center API error contract.
 */
export function isApiErrorPayload(data: unknown): data is ApiErrorPayload {
  if (!isRecord(data)) return false

  return typeof data.detail === 'string' && typeof data.code === 'string'
}

/**
 * Formats standard and legacy API errors into a user-facing message.
 */
export function formatApiError(data: unknown): string {
  const responseData = getResponseData(data)
  if (responseData !== undefined) return formatApiError(responseData)
  if (isApiErrorPayload(data)) return data.detail
  if (isRecord(data)) return formatLegacyObjectError(data)
  if (typeof data === 'string' && isJsonString(data)) return parseJsonError(data)
  if (data instanceof Error && data.message) return data.message

  return typeof data === 'string' && data ? data : FALLBACK_ERROR_MESSAGE
}

function getResponseData(data: unknown): unknown {
  if (!isRecord(data) || !isRecord(data.response)) return undefined
  return data.response.data
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
