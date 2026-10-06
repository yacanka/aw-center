import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { formatApiError, getApiErrorCode } from '@/shared/api/apiError'
import {
  buildAssistantRequest,
  fetchAssistantCatalog,
  sendAssistantMessage,
  type AssistantApplication,
  type AssistantCatalog,
  type AssistantHistoryMessage,
  type AssistantRequest,
  type AssistantSource
} from '@/features/assistant/api/assistant'

export type AssistantMessage = AssistantHistoryMessage & {
  applications?: AssistantApplication[]
  sources?: AssistantSource[]
}

/** In-memory conversation owned by one Pinia/session, including cancellation and stale-result fencing. */
export const useAssistantStore = defineStore('assistant', () => {
  const messages = ref<AssistantMessage[]>([])
  const pending = ref(false)
  const error = ref('')
  const errorCode = ref('')
  const catalog = ref<AssistantCatalog | null>(null)
  const catalogPending = ref(false)
  const catalogError = ref('')
  const failedRequest = ref<AssistantRequest | null>(null)
  const canRetry = computed(() => Boolean(failedRequest.value) && !pending.value)
  let chatGeneration = 0
  let catalogGeneration = 0
  let chatController: AbortController | null = null
  let catalogController: AbortController | null = null

  async function loadCatalog(force = false): Promise<void> {
    if (catalogPending.value || (catalog.value && !force)) return
    const generation = ++catalogGeneration
    const controller = new AbortController()
    catalogController = controller
    catalogPending.value = true
    catalogError.value = ''
    try {
      const response = await fetchAssistantCatalog(controller.signal)
      if (generation === catalogGeneration && !controller.signal.aborted) catalog.value = response
    } catch (cause) {
      if (generation === catalogGeneration && !controller.signal.aborted)
        catalogError.value = formatApiError(cause)
    } finally {
      if (generation === catalogGeneration) {
        catalogPending.value = false
        catalogController = null
      }
    }
  }

  /** False means the message was rejected locally; accepted requests retain their user turn on failure. */
  async function send(message: string, currentPath: string): Promise<boolean> {
    if (pending.value) return false
    let request: AssistantRequest
    try {
      request = buildAssistantRequest({
        message,
        history: messages.value,
        current_path: currentPath
      })
    } catch (cause) {
      error.value = formatApiError(cause)
      errorCode.value = 'VALIDATION_ERROR'
      return false
    }
    messages.value.push({ role: 'user', content: message })
    await execute(request)
    return true
  }

  async function execute(request: AssistantRequest): Promise<void> {
    const generation = ++chatGeneration
    const controller = new AbortController()
    chatController = controller
    pending.value = true
    error.value = ''
    errorCode.value = ''
    failedRequest.value = null
    try {
      const reply = await sendAssistantMessage(request, controller.signal)
      if (generation !== chatGeneration || controller.signal.aborted) return
      messages.value.push({
        role: 'assistant',
        content: reply.answer,
        applications: reply.applications,
        sources: reply.sources
      })
    } catch (cause) {
      if (generation !== chatGeneration || controller.signal.aborted) return
      error.value = formatApiError(cause)
      errorCode.value = getApiErrorCode(cause) || ''
      failedRequest.value = request
    } finally {
      if (generation === chatGeneration) {
        pending.value = false
        chatController = null
      }
    }
  }

  async function retry(): Promise<void> {
    if (!failedRequest.value || pending.value) return
    await execute(failedRequest.value)
  }

  function resetConversation(): void {
    // Never reset generations to an initial value: a previous request may still resolve after abort.
    chatGeneration += 1
    chatController?.abort()
    chatController = null
    messages.value = []
    pending.value = false
    error.value = ''
    errorCode.value = ''
    failedRequest.value = null
  }

  /** Called by the shared session-scope plugin for logout, identity changes and session expiry. */
  function $reset(): void {
    resetConversation()
    catalogGeneration += 1
    catalogController?.abort()
    catalogController = null
    catalog.value = null
    catalogPending.value = false
    catalogError.value = ''
  }

  return {
    messages,
    pending,
    error,
    errorCode,
    catalog,
    catalogPending,
    catalogError,
    canRetry,
    send,
    retry,
    loadCatalog,
    resetConversation,
    $reset
  }
})
