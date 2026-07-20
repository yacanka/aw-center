<template>
  <n-card title="Workflow accelerator">
    <template #header-extra>
      <n-button size="small" :loading="loading" @click="refresh">Refresh workflows</n-button>
    </template>
    <n-space vertical size="large">
      <n-alert type="info" :bordered="false">
        Run connected tools as one traceable process. Verified artifacts move between steps without
        a browser download and re-upload.
      </n-alert>
      <n-alert v-if="errorMessage" type="error" closable @close="errorMessage = ''">
        {{ errorMessage }}
      </n-alert>
      <n-grid cols="1 900:2" :x-gap="20" :y-gap="20">
        <n-grid-item>
          <WorkflowLauncher
            :recipes="recipes"
            :loading="loading"
            @queued="handleQueued"
            @error="errorMessage = $event"
          />
        </n-grid-item>
        <n-grid-item>
          <n-h3 style="margin-top: 0">Recent workflows</n-h3>
          <n-empty v-if="!loading && workflows.length === 0" description="No workflow runs yet." />
          <n-list v-else bordered>
            <WorkflowRunCard
              v-for="workflow in workflows"
              :key="workflow.id"
              :workflow="workflow"
              :cancelling="activeWorkflowId === workflow.id"
              @cancel="confirmCancel"
              @open-job="$emit('open-job', $event)"
            />
          </n-list>
        </n-grid-item>
      </n-grid>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import WorkflowLauncher from '@/components/jobs/WorkflowLauncher.vue'
import WorkflowRunCard from '@/components/jobs/WorkflowRunCard.vue'
import { formatApiError } from '@/services/apiError'
import {
  cancelWorkflowRun,
  fetchWorkflowRecipes,
  fetchWorkflowRuns,
  type WorkflowRecipe,
  type WorkflowRun
} from '@/services/workflows'

defineEmits<{ 'open-job': [jobId: string] }>()
const recipes = ref<WorkflowRecipe[]>([])
const workflows = ref<WorkflowRun[]>([])
const loading = ref(false)
const activeWorkflowId = ref('')
const errorMessage = ref('')

onMounted(refresh)
defineExpose({ refresh })

async function refresh(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    const catalogRequest = recipes.value.length
      ? Promise.resolve(recipes.value)
      : fetchWorkflowRecipes()
    const [catalog, page] = await Promise.all([catalogRequest, fetchWorkflowRuns()])
    recipes.value = catalog
    workflows.value = page.results
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    if (!silent) loading.value = false
  }
}

async function handleQueued(): Promise<void> {
  await refresh()
  window.$message.success('Connected workflow queued. Each step is now traceable in Job Center.')
}

function confirmCancel(workflow: WorkflowRun): void {
  window.$dialog.warning({
    title: 'Cancel workflow?',
    content: 'The active step will be cancelled. Completed artifacts remain auditable.',
    positiveText: 'Cancel workflow',
    negativeText: 'Keep running',
    onPositiveClick: () => performCancel(workflow)
  })
}

async function performCancel(workflow: WorkflowRun): Promise<void> {
  activeWorkflowId.value = workflow.id
  try {
    await cancelWorkflowRun(workflow.id)
    await refresh()
    window.$message.success('Workflow cancelled.')
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    activeWorkflowId.value = ''
  }
}
</script>
