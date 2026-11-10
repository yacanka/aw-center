export interface PasswordResetCapability {
  uid: string
  token: string
}

interface BrowserLocation {
  hash: string
  pathname: string
  search: string
}

interface BrowserHistory {
  state: unknown
  replaceState(data: unknown, unused: string, url?: string | URL | null): void
}

let capturedCapability: PasswordResetCapability | null = null

/**
 * Read a reset capability from the URL fragment and scrub it before Vue renders.
 * Fragments are not sent to the server, while replaceState removes them from
 * history, copied URLs, and later client-side navigation.
 */
export function consumePasswordResetCapability(
  location: BrowserLocation = window.location,
  history: BrowserHistory = window.history
): PasswordResetCapability | null {
  const rawFragment = location.hash.startsWith('#') ? location.hash.slice(1) : location.hash
  const parameters = new URLSearchParams(rawFragment)
  if (!parameters.has('uid') && !parameters.has('token')) return null

  history.replaceState(history.state, '', `${location.pathname}${location.search}`)
  const uid = parameters.get('uid') ?? ''
  const token = parameters.get('token') ?? ''
  return uid && token ? { uid, token } : null
}

/** Capture and scrub the initial login URL before router guards make requests. */
export function captureInitialPasswordResetCapability(
  location: BrowserLocation = window.location,
  history: BrowserHistory = window.history
): void {
  if (!location.pathname.endsWith('/login')) return
  capturedCapability = consumePasswordResetCapability(location, history)
}

/** Transfer the in-memory capability to the login view exactly once. */
export function takePasswordResetCapability(): PasswordResetCapability | null {
  const capability = capturedCapability
  capturedCapability = null
  return capability
}
