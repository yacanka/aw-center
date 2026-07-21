<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NDataTable, NSpace, NTag, NSpin, NUpload } from 'naive-ui'

import Watcher from '@/views/dcc/Watcher.vue'
import SubtaskGenerator from '@/views/dcc/SubtaskGenerator.vue'
import ExcelSubtaskGenerator from '@/views/dcc/ExcelSubtaskGenerator.vue'
import Unauthorized from '@/views/Unauthorized.vue'
import DCCCreator from '@/views/dcc/DCCCreator.vue'
import { useDccStore } from '@/stores/dcc'
import { IUser } from '@/models/jira'
import { nullCheck } from '@/utils/general'

const activeTab = ref('')
const route = useRoute()
const access = ref(true)
const sessionId = ref()
const store = useDccStore()
const jiraClientInfo = ref<IUser>()
const sessionRequiredTabs = new Set(['watcher', 'subtask', 'excelSubtask'])

async function connectJiraAccount() {
  try {
    jiraClientInfo.value = await store.checkSession(sessionId.value)
    store.setSessionId(sessionId.value)
    sessionField.value.visible = false
  } catch (e) {
    window.$message.error('Session ID is not valid. Enter new one.')
    showSessionPopup()
  }
}

const sessionField = ref({
  visible: false,
  title: 'Jira Session ID',
  onClick: connectJiraAccount
})

function onStart() {
  const savedTab =
    typeof route.query.dcc_job === 'string'
      ? 'dcc'
      : localStorage.getItem('jira>active_tab') || 'dcc'
  activeTab.value = savedTab
  if (sessionRequiredTabs.has(savedTab)) showSessionPopup()
}

function disconnectJiraAccount() {
  store.setSessionId('')
  jiraClientInfo.value = undefined
  sessionId.value = ''
  if (sessionRequiredTabs.has(activeTab.value)) showSessionPopup()
}

onMounted(async () => {
  //view.value = checkPermission("view_jira_dcc")
  onStart()
})

const handleTabChange = (tab: string) => {
  localStorage.setItem('jira>active_tab', tab)
  activeTab.value = tab
  if (sessionRequiredTabs.has(tab) && !store.getSessionId) showSessionPopup()
}

function showSessionPopup() {
  sessionField.value.visible = true
}

function continueWithoutSession() {
  activeTab.value = 'dcc'
  localStorage.setItem('jira>active_tab', 'dcc')
  sessionField.value.visible = false
}
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
            name: 'temporary-jira-session'
          }"
          placeholder="Temporary; never stored"
          @keydown.enter="sessionField.onClick"
        />
        <n-flex justify="center" style="margin-top: 10px">
          <n-button @click="continueWithoutSession">DCC Creator without session</n-button>
          <n-button type="info" @click="sessionField.onClick" :disabled="nullCheck(sessionId)"
            >Ok</n-button
          >
        </n-flex>
      </n-card>
    </n-flex>

    <n-space horizontal justify="space-between">
      <n-tabs
        v-if="!sessionField.visible"
        placement="top"
        v-model:value="activeTab"
        @update:value="handleTabChange"
        style="width: 80vw"
      >
        <template #suffix>
          <n-tag v-if="jiraClientInfo" type="success" closable @close="disconnectJiraAccount">
            Connected JIRA as {{ jiraClientInfo?.displayName }}
          </n-tag>
        </template>
        <n-tab-pane name="watcher" tab="Watcher">
          <n-divider style="margin: 0 0px 10px 0" />
          <Watcher />
        </n-tab-pane>
        <n-tab-pane name="dcc" tab="DCC Creator">
          <n-divider style="margin: 0 0px 10px 0" />
          <DCCCreator />
        </n-tab-pane>
        <n-tab-pane name="subtask" tab="Subtask Generator (List)">
          <n-divider style="margin: 0 0px 10px 0" />
          <SubtaskGenerator />
        </n-tab-pane>
        <n-tab-pane name="excelSubtask" tab="Subtask Generator (Excel)">
          <n-divider style="margin: 0 0px 10px 0" />
          <ExcelSubtaskGenerator />
        </n-tab-pane>
      </n-tabs>
    </n-space>
  </div>
  <div v-else>
    <Unauthorized />
  </div>
</template>

<style scoped>
:deep(.no-mask .n-modal-mask) {
  display: none !important;
}
</style>
