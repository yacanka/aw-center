const API_ROOT_SEGMENT = 'api'
const ABSOLUTE_URL_PATTERN = /^[a-z][a-z\d+.-]*:/i
const INVALID_URL_CHARACTERS = /[\\\u0000-\u001f\u007f]/

/** Build the canonical API root from an optional deployment origin or API-root override. */
export function normalizeApiBaseUrl(
  configuredValue?: string,
  browserHostname = runtimeBrowserHostname()
): string {
  const configured = configuredValue?.trim() || '/'
  if (INVALID_URL_CHARACTERS.test(configured) || /[?#]/.test(configured)) {
    throw new Error('The API URL contains unsupported characters.')
  }
  if (configured.startsWith('//')) {
    throw new Error('Protocol-relative API URLs are not allowed.')
  }

  if (ABSOLUTE_URL_PATTERN.test(configured)) {
    return normalizeAbsoluteApiBaseUrl(configured, browserHostname)
  }

  if (!configured.startsWith('/')) {
    throw new Error('The API URL must be an HTTP(S) URL or an absolute path.')
  }

  return appendApiRoot(configured)
}

/** Normalize a client request into a path relative to the canonical API root. */
export function normalizeApiRequestPath(path: string): string {
  const value = path.trim()
  if (
    !value ||
    value.startsWith('//') ||
    ABSOLUTE_URL_PATTERN.test(value) ||
    INVALID_URL_CHARACTERS.test(value) ||
    value.startsWith('?') ||
    value.includes('#')
  ) {
    throw new Error('API requests must use a non-empty relative path.')
  }

  const withoutLeadingSlash = value.replace(/^\/+/, '')
  const normalized = withoutLeadingSlash.startsWith(`${API_ROOT_SEGMENT}/`)
    ? withoutLeadingSlash.slice(API_ROOT_SEGMENT.length + 1)
    : withoutLeadingSlash
  assertSafePathSegments(normalized.split('?', 1)[0])
  return normalized
}

function assertSafePathSegments(pathname: string): void {
  try {
    const hasUnsafeSegment = pathname.split('/').some((segment) => {
      const decoded = decodeURIComponent(segment)
      return (
        decoded === '.' ||
        decoded === '..' ||
        decoded.includes('/') ||
        INVALID_URL_CHARACTERS.test(decoded)
      )
    })
    if (hasUnsafeSegment) throw new Error('unsafe')
  } catch {
    throw new Error('API request paths cannot contain traversal or encoded separators.')
  }
}

function normalizeAbsoluteApiBaseUrl(configured: string, browserHostname: string): string {
  const parsed = new URL(configured)
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('Only HTTP(S) API URLs are allowed.')
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error('The API URL cannot contain credentials, a query, or a fragment.')
  }
  if (browserHostname && parsed.hostname !== browserHostname) {
    throw new Error('The API URL hostname must match the browser hostname.')
  }

  parsed.pathname = appendApiRoot(parsed.pathname)
  return parsed.toString()
}

function runtimeBrowserHostname(): string {
  return typeof window === 'undefined' ? '' : window.location.hostname
}

function appendApiRoot(pathname: string): string {
  const normalized = `/${pathname}`.replace(/\/{2,}/g, '/').replace(/\/+$/, '')
  const apiPath = normalized.endsWith(`/${API_ROOT_SEGMENT}`)
    ? normalized
    : `${normalized}/${API_ROOT_SEGMENT}`
  return `${apiPath.replace(/^\/\//, '/')}/`
}
