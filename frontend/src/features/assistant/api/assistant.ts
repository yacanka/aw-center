import { apiClient } from '@/shared/api/http'

export type AssistantHistoryMessage = { role: 'user' | 'assistant'; content: string }
export type AssistantApplication = { id: string; title: string; path: string; description: string }
export type AssistantSource = { id: string; title: string; path: string }
export type AssistantCatalog = {
  status: 'configured' | 'unconfigured' | 'invalid'
  applications: AssistantApplication[]
}
export type AssistantRequest = {
  message: string
  history: AssistantHistoryMessage[]
  current_path: string
}
export type AssistantReply = {
  answer: string
  applications: AssistantApplication[]
  sources: AssistantSource[]
}

/** Match Python string length, including astral Unicode characters. */
export function assistantCharacterCount(value: string): number {
  return Array.from(value).length
}

/** Keep only complete recent messages within both character and serialized UTF-8 budgets. */
export function buildAssistantRequest(input: AssistantRequest): AssistantRequest {
  if (!input.message.trim()) throw new Error('Enter a message to send.')
  if (assistantCharacterCount(input.message) > 4000)
    throw new Error('Messages can contain up to 4,000 characters.')
  const currentPath = input.current_path.split(/[?#]/, 1)[0] || ''
  if (
    currentPath.length > 200 ||
    (currentPath && !/^\/[A-Za-z0-9/_-]*$/.test(currentPath)) ||
    currentPath.includes('//')
  )
    throw new Error('The current application path is invalid.')
  const history = input.history.slice(-12).map(({ role, content }) => {
    if (!['user', 'assistant'].includes(role) || !content.trim())
      throw new Error('Conversation history is invalid.')
    return { role, content }
  })
  const request = { message: input.message, history, current_path: currentPath }
  while (history.reduce((total, row) => total + assistantCharacterCount(row.content), 0) > 24000)
    history.shift()
  const encoder = new TextEncoder()
  while (encoder.encode(JSON.stringify(request)).byteLength > 65536 && history.length)
    history.shift()
  return request
}

/** Catalog reflects server configuration and authorized guides; it does not probe AI health. */
export async function fetchAssistantCatalog(signal?: AbortSignal): Promise<AssistantCatalog> {
  const response = await apiClient.get<AssistantCatalog>('integrations/assistant/catalog/', {
    signal
  })
  return response.data
}

/** Send a bounded conversation through the session/CSRF client with server-owned AI settings. */
export async function sendAssistantMessage(
  input: AssistantRequest,
  signal?: AbortSignal
): Promise<AssistantReply> {
  const response = await apiClient.post<AssistantReply>(
    'integrations/assistant/chat/',
    buildAssistantRequest(input),
    { signal, timeout: 35000 }
  )
  return response.data
}
