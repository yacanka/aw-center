<template>
  <n-space vertical size="large">
    <n-card>
      <n-space justify="space-between" align="center">
        <div>
          <n-h2 style="margin: 0">Workflow Accelerator</n-h2>
          <n-text depth="3">
            Upload a source file, let AW Center suggest matching automation recipes, or choose a
            recipe manually when no trigger is detected.
          </n-text>
        </div>
        <n-button @click="router.push({ name: 'jobs' })">Open Job Center</n-button>
      </n-space>
    </n-card>

    <n-tabs type="line" animated :value="activeTab" @update:value="openTab">
      <n-tab-pane name="accelerator" tab="Accelerator">
        <WorkflowAutomation @open-job="openJob" />
      </n-tab-pane>
      <n-tab-pane name="outlook" tab="Outlook Task">
        <OutlookContainer />
      </n-tab-pane>
    </n-tabs>
  </n-space>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import WorkflowAutomation from '@/components/jobs/WorkflowAutomation.vue'
import OutlookContainer from '@/views/OutlookContainer.vue'

const route = useRoute()
const router = useRouter()
const activeTab = computed(() => (route.name === 'acceleratorOutlook' ? 'outlook' : 'accelerator'))

function openTab(tabName: string): void {
  const name = tabName === 'outlook' ? 'acceleratorOutlook' : 'workflowAccelerator'
  router.push({ name })
}

function openJob(jobId: string): void {
  router.push({ name: 'jobs', query: { job: jobId } })
}
</script>
