<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import JiraConnection from '@/features/integrations/jira/components/JiraConnection.vue'
import Unauthorized from '@/features/session/pages/Unauthorized.vue'
import DCCCreator from '@/features/integrations/jira/pages/DCCCreator.vue'
import MeetingMinutes from './MeetingMinutes.vue'
import Watcher from '@/features/integrations/jira/pages/Watcher.vue'
import SubtaskGenerator from '@/features/integrations/jira/pages/SubtaskGenerator.vue'
import ExcelSubtaskGenerator from '@/features/integrations/jira/pages/ExcelSubtaskGenerator.vue'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { hasProjectJiraRole } from '@/features/projects/models/projectRegistry'

const DEFAULT_TAB = 'watcher'
const route = useRoute()
const router = useRouter()
const projectCatalog = useProjectCatalogStore()
const activeTab = ref(DEFAULT_TAB)
const initializing = ref(true)
const canAccessDcc = computed(() => projectCatalog.hasAnyRole('jira'))
const canCreateDcc = computed(() =>
  projectCatalog.jiraProjects.some((project) => hasProjectJiraRole(project.roles.jira, 'operator'))
)

/** Load role capability first, then resolve the server-owned JIRA connection. */
async function initialize(): Promise<void> {
  try {
    await projectCatalog.load()
    if (!canAccessDcc.value) return
    const requestedTab = route.query.jira_tab
    if (
      canCreateDcc.value &&
      typeof requestedTab === 'string' &&
      ['watcher', 'jira', 'minutes', 'subtask', 'excelSubtask'].includes(requestedTab)
    ) {
      activeTab.value = requestedTab
    } else if (typeof route.query.minutes_job === 'string' && canCreateDcc.value) {
      activeTab.value = 'minutes'
    } else if (typeof route.query.subtask_job === 'string' && canCreateDcc.value) {
      activeTab.value = 'subtask'
    } else if (typeof route.query.excel_subtask_job === 'string' && canCreateDcc.value) {
      activeTab.value = 'excelSubtask'
    } else if (typeof route.query.dcc_job === 'string' && canCreateDcc.value) {
      activeTab.value = 'jira'
    } else {
      activeTab.value = DEFAULT_TAB
    }
  } catch {
    // The catalog store owns the sanitized error; keeping this screen closed is intentional.
  } finally {
    initializing.value = false
  }
}

/** Keep tab navigation local to this visit; the JIRA session is shared by all tools. */
function handleTabChange(tab: string): void {
  activeTab.value = tab
  if (
    tab === 'minutes' ||
    route.query.jira_tab ||
    route.query.minutes_job ||
    route.query.subtask_job ||
    route.query.excel_subtask_job
  ) {
    void router.replace({ query: { ...route.query, jira_tab: tab } })
  }
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
  <JiraConnection v-else>
    <n-tabs
      v-model:value="activeTab"
      placement="top"
      style="width: 100%"
      @update:value="handleTabChange"
    >
      <n-tab-pane name="watcher" tab="Watcher">
        <n-divider style="margin: 0 0 10px" />
        <Watcher />
      </n-tab-pane>
      <n-tab-pane v-if="canCreateDcc" name="minutes" tab="Meeting Minutes">
        <MeetingMinutes />
      </n-tab-pane>
      <n-tab-pane v-if="canCreateDcc" name="jira" tab="DCC Creator">
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
  </JiraConnection>
</template>

<style scoped>
:deep(.no-mask .n-modal-mask) {
  display: none !important;
}
</style>
