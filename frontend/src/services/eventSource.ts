import axios from 'axios'
import { readString, STORAGE_KEYS } from '@/services/storage'

type StreamMessageHandler = ((event: MessageEvent<string>) => void) | null
type StreamErrorHandler = ((event: Event) => void) | null

export type AuthenticatedStreamSource = {
  onmessage: StreamMessageHandler
  onerror: StreamErrorHandler
  close: () => void
}

/**
 * Creates an authenticated SSE stream for protected streaming endpoints.
 */
export function createAuthenticatedEventSource(path: string): AuthenticatedStreamSource {
  const token = readString(STORAGE_KEYS.token)
  const url = createEventSourceUrl(path)
  if (token) return createFetchStreamSource(url, token)

  return new EventSource(url, { withCredentials: true })
}

function createEventSourceUrl(path: string) {
  const baseUrl = axios.defaults.baseURL || window.location.origin
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${baseUrl}${normalizedPath}`
}

function createFetchStreamSource(url: string, token: string): AuthenticatedStreamSource {
  const controller = new AbortController()
  const source = createStreamSource(controller)
  readFetchStream(url, token, controller, source)
  return source
}

function createStreamSource(controller: AbortController): AuthenticatedStreamSource {
  return {
    onmessage: null,
    onerror: null,
    close: () => controller.abort()
  }
}

async function readFetchStream(
  url: string,
  token: string,
  controller: AbortController,
  source: AuthenticatedStreamSource
) {
  try {
    const response = await fetchStreamResponse(url, token, controller)
    await parseStreamMessages(response, source)
  } catch {
    if (!controller.signal.aborted) source.onerror?.(new Event('error'))
  }
}

async function fetchStreamResponse(url: string, token: string, controller: AbortController) {
  const response = await fetch(url, {
    headers: { Authorization: `Token ${token}` },
    signal: controller.signal
  })
  if (!response.ok || !response.body) throw new Error(`Stream failed: ${response.status}`)
  return response
}

async function parseStreamMessages(response: Response, source: AuthenticatedStreamSource) {
  const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer = emitBufferedMessages(buffer + value, source)
  }
}

function emitBufferedMessages(buffer: string, source: AuthenticatedStreamSource) {
  const chunks = buffer.split('\n\n')
  const remainder = chunks.pop() || ''
  chunks
    .map(parseSseData)
    .filter(Boolean)
    .forEach((data) => {
      source.onmessage?.(new MessageEvent('message', { data }))
    })
  return remainder
}

function parseSseData(chunk: string) {
  const lines = chunk.split('\n').filter((line) => line.startsWith('data:'))
  return lines.map((line) => line.slice(5).trimStart()).join('\n')
}
