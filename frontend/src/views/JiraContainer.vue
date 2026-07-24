<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import type { IUser } from '@/models/jira'
import { useDccStore } from '@/stores/dcc'
import { nullCheck } from '@/utils/general'
import Unauthorized from '@/views/Unauthorized.vue'
import DCCCreator from '@/views/dcc/DCCCreator.vue'
import ExcelSubtaskGenerator from '@/views/dcc/ExcelSubtaskGenerator.vue'
import SubtaskGenerator from '@/views/dcc/SubtaskGenerator.vue'
import Watcher from '@/views/dcc/Watcher.vue'

const DEFAULT_TAB = 'watcher'
const route = useRoute()
const store = useDccStore()
const activeTab = ref(DEFAULT_TAB)
const access = ref(true)
const sessionId = ref(store.getSessionId)
const jiraClientInfo = ref<IUser>()
const sessionField = ref({ visible: false, title: 'JIRA Session ID' })

/** Validate and persist the entered JIRA session for all JIRA tools. */
async function connectJiraAccount(): Promise<void> {
  const credential = sessionId.value.trim()
  try {
    jiraClientInfo.value = await store.checkSession(credential)
    store.setSessionId(credential)
    sessionField.value.visible = false
  } catch {
    if (store.getSessionId === credential) store.setSessionId('')
    window.$message.error('Session ID is not valid. Enter a new one.')
    showSessionPopup()
  }
}

/** Restore the JIRA workspace only after a valid browser-saved session exists. */
async function initialize(): Promise<void> {
  activeTab.value = typeof route.query.dcc_job === 'string' ? 'dcc' : DEFAULT_TAB
  await ensureJiraSession()
}

/** Remove the browser-persisted JIRA session and connected user details. */
function disconnectJiraAccount(): void {
  store.setSessionId('')
  jiraClientInfo.value = undefined
  sessionId.value = ''
  showSessionPopup()
}

/** Keep tab navigation local to this visit; the JIRA session is shared by all tools. */
function handleTabChange(tab: string): void {
  activeTab.value = tab
}

/** Reuse and validate the locally saved session, or ask the user for one. */
async function ensureJiraSession(): Promise<void> {
  if (jiraClientInfo.value) return
  sessionId.value = store.getSessionId
  if (sessionId.value) await connectJiraAccount()
  else showSessionPopup()
}

function showSessionPopup(): void {
  sessionField.value.visible = true
}

onMounted(initialize)
</script>

<template>
  <div v-if="access">
    <n-flex v-if="sessionField.visible" justify="center">
      <n-card :title="sessionField.title" style="width: 50vw; min-width: 300px">
        <n-input
          v-model:value="sessionId"
          type="password"
          show-password-on="click"
          :input-props="{
            autocomplete: 'one-time-code',
            name: 'jira-session-id'
          }"
          placeholder="Enter JSESSIONID to use JIRA tools"
          @keydown.enter="connectJiraAccount"
        />
        <n-flex justify="center" style="margin-top: 10px">
          <n-button type="info" :disabled="nullCheck(sessionId)" @click="connectJiraAccount">
            Connect
          </n-button>
        </n-flex>
      </n-card>
    </n-flex>

    <n-space horizontal justify="space-between">
      <n-tabs
        v-if="!sessionField.visible"
        v-model:value="activeTab"
        placement="top"
        style="width: 80vw"
        @update:value="handleTabChange"
      >
        <template #suffix>
          <n-tag v-if="jiraClientInfo" type="success" closable @close="disconnectJiraAccount">
            Connected to JIRA as {{ jiraClientInfo.displayName }}
          </n-tag>
        </template>
        <n-tab-pane name="dcc" tab="DCC Creator">
          <n-divider style="margin: 0 0 10px" />
          <DCCCreator />
        </n-tab-pane>
        <n-tab-pane name="watcher" tab="Watcher">
          <n-divider style="margin: 0 0 10px" />
          <Watcher />
        </n-tab-pane>
        <n-tab-pane name="subtask" tab="Subtask Generator (List)">
          <n-divider style="margin: 0 0 10px" />
          <SubtaskGenerator />
        </n-tab-pane>
        <n-tab-pane name="excelSubtask" tab="Subtask Generator (Excel)">
          <n-divider style="margin: 0 0 10px" />
          <ExcelSubtaskGenerator />
        </n-tab-pane>
      </n-tabs>
    </n-space>
  </div>
  <Unauthorized v-else />
</template>

<style scoped>
:deep(.no-mask .n-modal-mask) {
  display: none !important;
}
</style>
