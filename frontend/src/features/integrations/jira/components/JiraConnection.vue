<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useThemeVars } from 'naive-ui'
import { useJiraStore } from '@/features/integrations/jira/stores/jira'
import type { JiraAuthMethod } from '@/features/integrations/jira/api/jiraSession'
import { useSessionStore } from '@/features/session/stores/session'

const AUTH_METHOD_STORAGE_KEY = 'jira>auth-method'
const AUTH_METHODS = [
  { name: 'session_id', label: 'Session ID' },
  { name: 'personal_access_token', label: 'Personal Access Token' }
] as const
const store = useJiraStore()
const themeVars = useThemeVars()
const sessionStore = useSessionStore()
const initializing = ref(true)
const sessionId = ref('')
const authMethod = ref<JiraAuthMethod>(restoreAuthMethod())
const connecting = ref(false)
const sessionField = ref({ visible: false, title: 'Connect to JIRA' })
const credentialLabel = computed(() =>
  authMethod.value === 'personal_access_token' ? 'Personal Access Token' : 'Session ID'
)
const connectedAccount = computed(() => {
  const user = store.jiraConnection.user
  if (!user) return 'Connected to JIRA'
  if (!user.display_name || user.display_name === user.username) return `JIRA: ${user.username}`
  return user.username
    ? `JIRA: ${user.display_name} (${user.username})`
    : `JIRA: ${user.display_name}`
})
/** Exchange the entered credential without retaining it in browser state. */
async function connectJiraAccount(): Promise<void> {
  const credential = sessionId.value.trim()
  if (connecting.value || !credential) return
  connecting.value = true
  try {
    await store.connectJira(credential, authMethod.value)
    sessionField.value.visible = false
  } catch {
    // The store presents the safe API error, including PAT account mismatches.
    showSessionPopup()
  } finally {
    sessionId.value = ''
    connecting.value = false
  }
}

/** Remember only the selected method, never the credential entered for it. */
function restoreAuthMethod(): JiraAuthMethod {
  try {
    const saved = window.localStorage.getItem(AUTH_METHOD_STORAGE_KEY)
    if (saved === 'session_id' || saved === 'personal_access_token') return saved
  } catch {
    // Storage may be unavailable; the connection form must remain usable.
  }
  return 'session_id'
}

function changeAuthMethod(method: JiraAuthMethod): void {
  if (connecting.value || authMethod.value === method) return
  sessionId.value = ''
  authMethod.value = method
  try {
    window.localStorage.setItem(AUTH_METHOD_STORAGE_KEY, method)
  } catch {
    // A storage failure must not prevent switching authentication methods.
  }
}

function handleAuthTabKeydown(event: KeyboardEvent): void {
  if (connecting.value) return
  let method: JiraAuthMethod
  if (event.key === 'Home') method = 'session_id'
  else if (event.key === 'End') method = 'personal_access_token'
  else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    method = authMethod.value === 'session_id' ? 'personal_access_token' : 'session_id'
  } else return
  event.preventDefault()
  changeAuthMethod(method)
  document.getElementById(`jira-auth-${method}`)?.focus()
}

/** Revoke the server-side JIRA connection and clear its public state. */
async function disconnectJiraAccount(): Promise<void> {
  await store.disconnectJira()
  sessionId.value = ''
  showSessionPopup()
}

/** Reuse the server-owned connection, or ask for a one-time credential exchange. */
async function ensureJiraSession(): Promise<void> {
  try {
    const connection = await store.fetchJiraConnection()
    if (connection.state !== 'connected') showSessionPopup()
  } catch {
    showSessionPopup()
  } finally {
    initializing.value = false
  }
}

function showSessionPopup(): void {
  sessionField.value.visible = true
}

onMounted(ensureJiraSession)
</script>
<template>
  <n-spin v-if="initializing" />
  <div v-else>
    <n-flex v-if="sessionField.visible" justify="center">
      <n-card :title="sessionField.title" class="jira-session-card">
        <n-tabs
          :value="authMethod"
          type="segment"
          class="jira-auth-tabs"
          role="tablist"
          aria-label="JIRA authentication method"
          @update:value="changeAuthMethod"
          @keydown="handleAuthTabKeydown"
        >
          <n-tab
            v-for="method in AUTH_METHODS"
            :id="`jira-auth-${method.name}`"
            :key="method.name"
            :name="method.name"
            role="tab"
            aria-controls="jira-credentials"
            :aria-selected="authMethod === method.name"
            :aria-disabled="connecting"
            :tabindex="authMethod === method.name ? 0 : -1"
            :disabled="connecting"
            @keydown.enter.prevent="changeAuthMethod(method.name)"
            @keydown.space.prevent="changeAuthMethod(method.name)"
            >{{ method.label }}</n-tab
          >
        </n-tabs>
        <form
          id="jira-credentials"
          role="tabpanel"
          :aria-labelledby="`jira-auth-${authMethod}`"
          :aria-busy="connecting"
          @submit.prevent="connectJiraAccount"
        >
          <n-form-item
            v-if="authMethod === 'personal_access_token'"
            label="AW Center username"
            :label-props="{ for: 'jira-username' }"
          >
            <n-input
              :value="sessionStore.user?.username || ''"
              readonly
              :input-props="{ id: 'jira-username', autocomplete: 'username' }"
            />
          </n-form-item>
          <n-form-item :label="credentialLabel" :label-props="{ for: 'jira-credential' }">
            <n-input
              :key="authMethod"
              v-model:value="sessionId"
              type="password"
              show-password-on="click"
              :disabled="connecting"
              :input-props="{
                id: 'jira-credential',
                autocomplete: 'one-time-code',
                name:
                  authMethod === 'personal_access_token'
                    ? 'jira-personal-access-token'
                    : 'jira-session-id'
              }"
              :placeholder="
                authMethod === 'personal_access_token'
                  ? 'Enter your personal access token'
                  : 'Enter JSESSIONID to use JIRA tools'
              "
            />
          </n-form-item>
          <n-flex justify="center">
            <n-button
              attr-type="submit"
              aria-label="Connect"
              type="info"
              :loading="connecting"
              :disabled="connecting || !sessionId.trim()"
            >
              Connect
            </n-button>
          </n-flex>
        </form>
      </n-card>
    </n-flex>

    <div class="jira-tabs">
      <n-flex
        v-if="!sessionField.visible && store.isJiraConnected"
        justify="end"
        class="jira-connection-status"
      >
        <n-tag type="success" class="jira-account-tag" :title="connectedAccount">
          <span class="jira-account-name">{{ connectedAccount }}</span>
          <template #icon>
            <n-button
              text
              size="tiny"
              aria-label="Disconnect from JIRA"
              @click="disconnectJiraAccount"
            >
              ×
            </n-button>
          </template>
        </n-tag>
      </n-flex>
      <slot v-if="!sessionField.visible && store.isJiraConnected" />
    </div>
  </div>
</template>
<style scoped>
.jira-session-card {
  width: min(100%, 680px);
}

.jira-auth-tabs {
  width: 100%;
  margin-bottom: 20px;
}

.jira-auth-tabs :deep(.n-tabs-tab-wrapper) {
  min-width: 0;
}

.jira-auth-tabs :deep(.n-tabs-tab) {
  min-height: 44px;
  height: 100%;
  text-align: center;
}

.jira-auth-tabs :deep(.n-tabs-tab__label) {
  white-space: normal;
}

.jira-auth-tabs :deep(.n-tabs-tab:focus-visible) {
  outline: 2px solid v-bind('themeVars.primaryColor');
  outline-offset: -2px;
}

.jira-connection-status {
  margin-bottom: 8px;
}

.jira-account-tag {
  max-width: 100%;
}

.jira-account-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.jira-account-tag :deep(.n-tag__content) {
  min-width: 0;
}

.jira-tabs {
  min-width: 0;
  width: 100%;
}
</style>
