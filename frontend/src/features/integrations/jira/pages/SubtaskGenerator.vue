<template>
  <n-flex justify="center">
    <n-card title="JIRA Subtask Generator" style="width: 90%; min-width: 300px">
      <n-grid cols="6" x-gap="12" y-gap="18">
        <n-grid-item span="6">
          <div class="subtask-generator-header">
            <n-input
              v-model:value="generator.url"
              type="url"
              placeholder="Enter Url"
              @keydown.enter.prevent
            />
            <n-flex class="subtask-generator-actions">
              <n-button
                type="primary"
                ghost
                :loading="fieldLoading"
                :disabled="isFieldLoadDisabled"
                @click="loadSubtaskFields"
              >
                Load Fields
              </n-button>
              <n-button type="info" ghost :disabled="checkGenerateStatus()" @click="createSubtasks">
                Generate
              </n-button>
            </n-flex>
          </div>
        </n-grid-item>
        <n-grid-item v-if="loadingBar.show" span="6">
          <n-flex vertical size="small" class="subtask-progress">
            <n-ellipsis v-if="loadingBar.content">
              {{ loadingBar.content }}
            </n-ellipsis>
            <n-progress
              type="line"
              :status="loadingBar.status"
              :percentage="loadingBar.percentage"
              indicator-placement="outside"
              :height="30"
              :processing="loadingBar.status == 'default'"
            />
          </n-flex>
        </n-grid-item>
        <n-grid-item span="6">
          <subtask-list v-model:list="generator.list" :fields="subtaskFields" />
        </n-grid-item>
      </n-grid>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import SubtaskList from '@/features/integrations/jira/components/SubtaskList.vue'
import { useJiraStore } from '@/features/integrations/jira/stores/jira'
import { useSubtaskProgress } from '@/features/integrations/jira/composables/useSubtaskProgress'
import type { IJiraField, ISubtaskItem } from '@/features/integrations/jira/models/jira'
import { toSubtaskRequest } from '@/features/integrations/jira/models/subtaskItems'
import {
  createManualSubtaskJob,
  fetchSubtaskFields
} from '@/features/integrations/jira/api/jiraSubtasks'
import { formatApiError } from '@/shared/api/apiError'

const jiraStore = useJiraStore()
const generator = ref({ url: '', list: [] as ISubtaskItem[] })
const subtaskFields = ref<IJiraField[]>([])
const fieldLoading = ref(false)
const { loadingBar, busy, submit } = useSubtaskProgress('subtask_job')
const isUrlEmpty = computed(() => !generator.value.url.trim())
const isFieldLoadDisabled = computed(
  () => isUrlEmpty.value || fieldLoading.value || !jiraStore.isJiraConnected
)

function checkGenerateStatus(): boolean {
  return busy.value || isUrlEmpty.value || !jiraStore.isJiraConnected
}

async function loadSubtaskFields(): Promise<void> {
  if (isFieldLoadDisabled.value) return
  fieldLoading.value = true
  try {
    const result = await fetchSubtaskFields(generator.value.url)
    subtaskFields.value = result.fields
    window.$notification.success({
      title: 'Fields Loaded',
      description: `${result.issue} sub-task fields are ready.`,
      duration: 3000
    })
  } catch (error) {
    subtaskFields.value = []
    window.$notification.error({
      title: 'Field Load Error',
      description: formatApiError(error),
      duration: 5000
    })
  } finally {
    fieldLoading.value = false
  }
}

async function createSubtasks(): Promise<void> {
  if (checkGenerateStatus()) return
  if (!generator.value.list.length) {
    window.$notification.warning({
      title: 'Warning',
      description: 'No subtask to create.',
      duration: 3000
    })
    return
  }
  const issue = generator.value.url
  const items = generator.value.list.map(toSubtaskRequest)
  await submit(() => createManualSubtaskJob(issue, items))
}
</script>

<style scoped>
.subtask-generator-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
}

.subtask-progress {
  margin-top: -8px;
}

@media (max-width: 640px) {
  .subtask-generator-header {
    grid-template-columns: minmax(0, 1fr);
  }

  .subtask-generator-actions > .n-button {
    flex: 1;
  }
}
</style>
