<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useDccStore } from '@/features/dcc/stores/dcc'
import { nullCheck } from '@/shared/utils/general'
import Unauthorized from '@/features/session/pages/Unauthorized.vue'
import DCCCreator from '@/features/dcc/pages/DCCCreator.vue'
import Watcher from '@/features/dcc/pages/Watcher.vue'
import SubtaskGenerator from '@/features/dcc/pages/SubtaskGenerator.vue'
import ExcelSubtaskGenerator from '@/features/dcc/pages/ExcelSubtaskGenerator.vue'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { hasProjectDccRole } from '@/features/projects/models/projectRegistry'

const DEFAULT_TAB = 'watcher'
const route = useRoute()
const router = useRouter()
const store = useDccStore()
const projectCatalog = useProjectCatalogStore()
const activeTab = ref(DEFAULT_TAB)
const initializing = ref(true)
const sessionId = ref('')
const sessionField = ref({ visible: false, title: 'JIRA Session ID' })
const canAccessDcc = computed(() => projectCatalog.hasAnyRole('dcc'))
const canCreateDcc = computed(() =>
  projectCatalog.dccProjects.some((project) => hasProjectDccRole(project.roles.dcc, 'operator'))
)

/** Exchange the entered credential without retaining it in browser state. */
async function connectJiraAccount(): Promise<void> {
  const credential = sessionId.value.trim()
  try {
    await store.connectJira(credential)
    sessionField.value.visible = false
  } catch {
    window.$message.error('Session ID is not valid. Enter a new one.')
    showSessionPopup()
  } finally {
    sessionId.value = ''
  }
}

/** Load role capability first, then resolve the server-owned JIRA connection. */
async function initialize(): Promise<void> {
  try {
    await projectCatalog.load()
    if (!canAccessDcc.value) return
    if (
      canCreateDcc.value &&
      (route.query.jira_tab === 'subtask' || route.query.jira_tab === 'excelSubtask')
    ) {
      activeTab.value = route.query.jira_tab
    } else if (typeof route.query.subtask_job === 'string' && canCreateDcc.value) {
      activeTab.value = 'subtask'
    } else if (typeof route.query.excel_subtask_job === 'string' && canCreateDcc.value) {
      activeTab.value = 'excelSubtask'
    } else if (typeof route.query.dcc_job === 'string' && canCreateDcc.value) {
      activeTab.value = 'dcc'
    } else {
      activeTab.value = DEFAULT_TAB
    }
    await ensureJiraSession()
  } catch {
    // The catalog store owns the sanitized error; keeping this screen closed is intentional.
  } finally {
    initializing.value = false
  }
}

/** Revoke the server-side JIRA connection and clear its public state. */
async function disconnectJiraAccount(): Promise<void> {
  await store.disconnectJira()
  sessionId.value = ''
  showSessionPopup()
}

/** Keep tab navigation local to this visit; the JIRA session is shared by all tools. */
function handleTabChange(tab: string): void {
  activeTab.value = tab
  if (route.query.subtask_job || route.query.excel_subtask_job) {
    void router.replace({ query: { ...route.query, jira_tab: tab } })
  }
}

/** Reuse the server-owned connection, or ask for a one-time credential exchange. */
async function ensureJiraSession(): Promise<void> {
  try {
    const connection = await store.fetchJiraConnection()
    if (connection.state !== 'connected') showSessionPopup()
  } catch {
    showSessionPopup()
  }
}

function showSessionPopup(): void {
  sessionField.value.visible = true
}

onMounted(initialize)
</script>

<template>
  <n-spin v-if="initializing" />
  <n-result
    v-else-if="projectCatalog.status === 'error'"
    status="warning"
    title="Project catalog unavailable"
    description="JIRA actions remain disabled until project roles can be verified."
  />
  <Unauthorized v-else-if="!canAccessDcc" />
  <div v-else>
    <n-flex v-if="sessionField.visible" justify="center">
      <n-card :title="sessionField.title" class="jira-session-card">
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

    <div class="jira-tabs">
      <n-tabs
        v-if="!sessionField.visible"
        v-model:value="activeTab"
        placement="top"
        style="width: 100%"
        @update:value="handleTabChange"
      >
        <template #suffix>
          <n-tag
            v-if="store.isJiraConnected"
            type="success"
            closable
            @close="disconnectJiraAccount"
          >
            Connected to JIRA
          </n-tag>
        </template>
        <n-tab-pane name="watcher" tab="Watcher">
          <n-divider style="margin: 0 0 10px" />
          <Watcher />
        </n-tab-pane>
        <n-tab-pane v-if="canCreateDcc" name="dcc" tab="DCC Creator">
          <n-divider style="margin: 0 0 10px" />
          <DCCCreator />
        </n-tab-pane>
        <n-tab-pane v-if="canCreateDcc" name="subtask" tab="Subtask Generator (List)">
          <n-divider style="margin: 0 0 10px" />
          <SubtaskGenerator />
        </n-tab-pane>
        <n-tab-pane v-if="canCreateDcc" name="excelSubtask" tab="Subtask Generator (Excel)">
          <n-divider style="margin: 0 0 10px" />
          <ExcelSubtaskGenerator />
        </n-tab-pane>
      </n-tabs>
    </div>
  </div>
</template>

<style scoped>
:deep(.no-mask .n-modal-mask) {
  display: none !important;
}

.jira-session-card {
  width: min(100%, 680px);
}

.jira-tabs {
  min-width: 0;
  width: 100%;
}
</style>
