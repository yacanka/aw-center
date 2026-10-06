<template>
  <n-drawer
    :show="show"
    width="min(440px, 100vw)"
    placement="right"
    aria-label="AW Center Assistant"
    @update:show="emit('update:show', $event)"
    @after-enter="focusInput"
    @after-leave="restoreFocus"
  >
    <n-drawer-content
      title="AW Center Assistant"
      :native-scrollbar="false"
      :body-content-style="{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        padding: '16px'
      }"
    >
      <template #header>
        <div class="panel-header">
          <strong>AW Center Assistant</strong
          ><n-button
            class="touch-control"
            quaternary
            aria-label="Close assistant"
            @click="emit('update:show', false)"
            >Close</n-button
          >
        </div>
      </template>
      <section
        class="assistant-panel"
        data-testid="assistant-panel"
        aria-label="AW Center Assistant"
      >
        <p class="service-disclosure">
          Messages are sent to the configured AI service. Avoid sharing sensitive information.
        </p>
        <div class="panel-toolbar">
          <n-button class="touch-control" @click="newConversation">New chat</n-button>
        </div>
        <n-spin v-if="store.catalogPending" size="small" aria-label="Loading applications" />
        <n-alert v-if="store.catalogError" type="warning" class="panel-alert"
          ><span class="plain-error">{{ store.catalogError }}</span
          ><n-button class="touch-control" @click="store.loadCatalog(true)"
            >Reload applications</n-button
          ></n-alert
        >
        <n-alert v-if="store.catalog?.status === 'unconfigured'" type="info" class="panel-alert"
          >AI service is not configured. You can still open the available applications
          below.</n-alert
        >
        <n-alert v-else-if="store.catalog?.status === 'invalid'" type="warning" class="panel-alert"
          >AI service configuration needs attention. You can still open the available applications
          below.</n-alert
        >
        <div
          ref="conversation"
          class="conversation"
          role="log"
          aria-label="Assistant conversation"
          aria-live="polite"
          aria-relevant="additions text"
          :aria-busy="store.pending"
        >
          <p v-if="!store.messages.length && !showFallback" class="empty-copy">
            Ask which application can help, or how to use an AW Center tool.
          </p>
          <AssistantMessage
            v-for="(message, index) in store.messages"
            :key="index"
            :message="message"
          />
          <AssistantMessage
            v-if="showFallback && store.catalog"
            catalog
            :message="{
              role: 'assistant',
              content: '',
              applications: store.catalog.applications
            }"
          />
          <p v-if="store.pending" role="status">Assistant is thinking…</p>
        </div>
        <p class="source-disclosure">
          Application guides are references, not a guarantee of answer accuracy.
        </p>
        <n-alert v-if="store.error" type="warning" class="panel-alert" role="alert"
          ><span class="plain-error">{{ store.error }}</span>
          <p v-if="store.errorCode === 'THROTTLED'">Wait a minute before trying again.</p>
          <n-button v-if="store.canRetry" class="touch-control" @click="store.retry"
            >Try again</n-button
          ></n-alert
        >
        <form class="composer" @submit.prevent="submit">
          <label for="assistant-message">Message</label>
          <n-input
            ref="input"
            v-model:value="draft"
            type="textarea"
            :disabled="store.pending || !configured"
            :autosize="{ minRows: 2, maxRows: 5 }"
            placeholder="How can I use AW Center?"
            :input-props="{
              id: 'assistant-message',
              'aria-label': 'Message to assistant',
              'aria-describedby': tooLong ? 'assistant-message-limit' : undefined
            }"
            @keydown="onKeydown"
          />
          <div class="composer-actions">
            <span id="assistant-message-limit" :class="{ 'limit-error': tooLong }"
              >{{ characterCount.toLocaleString('en-US') }} / 4,000</span
            ><n-button
              class="touch-control"
              type="primary"
              attr-type="submit"
              :disabled="!canSend"
              :loading="store.pending"
              >Send</n-button
            >
          </div>
        </form>
      </section>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { NDrawer, NDrawerContent, useThemeVars, type InputInst } from 'naive-ui'
import { useRoute } from 'vue-router'
import { useAssistantStore } from '@/features/assistant/stores/assistant'
import { assistantCharacterCount } from '@/features/assistant/api/assistant'
import AssistantMessage from './AssistantMessage.vue'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()
const store = useAssistantStore()
const route = useRoute()
const themeVars = useThemeVars()
const draft = ref('')
const input = ref<InputInst | null>(null)
const conversation = ref<HTMLElement | null>(null)
let returnFocus: HTMLElement | null = null
const configured = computed(() => store.catalog?.status === 'configured')
const showFallback = computed(() =>
  Boolean(store.catalog && (!configured.value || store.errorCode === 'AI_CONFIGURATION_ERROR'))
)
const characterCount = computed(() => assistantCharacterCount(draft.value))
const tooLong = computed(() => characterCount.value > 4000)
const canSend = computed(
  () => configured.value && !store.pending && Boolean(draft.value.trim()) && !tooLong.value
)

watch(
  () => props.show,
  async (show) => {
    if (!show) return
    returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await store.loadCatalog()
    if (props.show) await focusInput()
  },
  { immediate: true }
)
watch(
  () => [store.messages.length, store.pending],
  async () => {
    await nextTick()
    if (conversation.value) conversation.value.scrollTop = conversation.value.scrollHeight
  }
)

async function focusInput(): Promise<void> {
  await nextTick()
  if (configured.value && !store.pending) input.value?.focus()
}
function restoreFocus(): void {
  returnFocus?.focus()
}
async function newConversation(): Promise<void> {
  store.resetConversation()
  draft.value = ''
  await focusInput()
}
async function submit(): Promise<void> {
  if (!canSend.value) return
  const message = draft.value
  draft.value = ''
  await store.send(message, route.path)
  if (props.show) await focusInput()
}
function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  void submit()
}
</script>

<style scoped>
.assistant-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
  min-width: 0;
  font-family: v-bind('themeVars.fontFamily');
  color: v-bind('themeVars.textColor1');
}
.panel-header {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  width: 100%;
}
.panel-toolbar {
  display: flex;
  justify-content: flex-end;
}
.service-disclosure,
.source-disclosure,
.empty-copy {
  color: v-bind('themeVars.textColor2');
  margin: 0;
  line-height: 1.5;
}
.source-disclosure {
  font-size: 12px;
}
.conversation {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  min-height: 80px;
  overflow-y: auto;
  padding: 3px;
  overscroll-behavior: contain;
}
.panel-alert {
  flex-shrink: 0;
}
.plain-error {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.composer {
  display: grid;
  gap: 8px;
  flex-shrink: 0;
  padding-bottom: env(safe-area-inset-bottom);
}
.composer-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  color: v-bind('themeVars.textColor3');
}
.limit-error {
  color: v-bind('themeVars.errorColor');
}
.touch-control {
  min-width: 44px;
  min-height: 44px;
}
.touch-control:focus-visible {
  outline: 2px solid v-bind('themeVars.primaryColor');
  outline-offset: 2px;
}
</style>
