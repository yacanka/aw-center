<script setup lang="ts">
import {
  Add24Regular,
  Branch24Regular,
  ChannelAdd24Regular,
  DataBarVertical24Regular,
  DocumentArrowDown20Regular,
  Settings24Regular
} from '@vicons/fluent'
import ImportAuditHistory from '@/components/compdoc/ImportAuditHistory.vue'
import CompDocBulkDelete from '@/components/compdoc/CompDocBulkDelete.vue'

defineProps<{
  project: string
  canImport: boolean
  canCreate: boolean
  canDelete: boolean
  canViewAudits: boolean
  count: number
  pageSize: number
  checking: boolean
  progress: { completed: number; total: number }
}>()
const emit = defineEmits<{
  import: []
  create: []
  summary: []
  check: []
  export: []
  settings: []
  pageSize: [value: number]
}>()

function updatePageSize(value: number | null) {
  if (value) emit('pageSize', value)
}
</script>

<template>
  <n-space justify="space-between">
    <n-space>
      <n-button v-if="canImport" :focusable="false" @click="emit('import')">
        <template #icon
          ><n-icon size="24"><ChannelAdd24Regular /></n-icon
        ></template>
        Import
      </n-button>
      <ImportAuditHistory :allowed="canViewAudits" :project="project" />
      <n-button v-if="canCreate" :focusable="false" @click="emit('create')">
        <template #icon
          ><n-icon size="24"><Add24Regular /></n-icon
        ></template>
        New
      </n-button>
      <n-button :focusable="false" @click="emit('summary')">
        <template #icon
          ><n-icon size="24"><DataBarVertical24Regular /></n-icon
        ></template>
        Summary
      </n-button>
      <n-button :focusable="false" :loading="checking" :disabled="checking" @click="emit('check')">
        <template #icon
          ><n-icon size="24"><Branch24Regular /></n-icon
        ></template>
        Check Issues
      </n-button>
      <n-text v-if="checking || progress.total" depth="3">
        Checked {{ progress.completed }}/{{ progress.total }}
      </n-text>
    </n-space>
    <n-space>
      <n-button ghost color="#65B25D" :focusable="false" @click="emit('export')">
        <template #icon
          ><n-icon size="24"><DocumentArrowDown20Regular /></n-icon
        ></template>
        Export Excel
      </n-button>
      <CompDocBulkDelete v-if="canDelete" :project="project" :count="count" />
    </n-space>
  </n-space>
  <n-flex justify="end" style="margin: 16px 0 4px">
    <n-space>
      <strong>Page Size:</strong>
      <n-input-number
        :value="pageSize"
        size="tiny"
        style="width: 56px"
        :show-button="false"
        :min="1"
        :max="200"
        @update:value="updatePageSize"
      />
    </n-space>
    <n-text><strong>Total:</strong> {{ count }}</n-text>
    <n-button size="tiny" :focusable="false" @click="emit('settings')">
      <template #icon><Settings24Regular /></template>
    </n-button>
  </n-flex>
</template>
