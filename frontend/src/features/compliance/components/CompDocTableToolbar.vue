<script setup lang="ts">
import {
  Add24Regular,
  Branch24Regular,
  ChannelAdd24Regular,
  DataBarVertical24Regular,
  DatabaseLink20Regular,
  DocumentArrowDown20Regular,
  Settings24Regular
} from '@vicons/fluent'
import { ref } from 'vue'
import ImportAuditHistory from '@/features/compliance/components/ImportAuditHistory.vue'

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
  importDoors: []
  create: []
  summary: []
  check: []
  export: []
  settings: []
  pageSize: [value: number]
  search: [value: string]
  quickFilter: [value: string]
}>()
const search = ref('')

function updatePageSize(value: number | null) {
  if (value) emit('pageSize', value)
}
</script>

<template>
  <n-flex justify="space-between" class="toolbar-primary">
    <n-flex>
      <n-button v-if="canImport" @click="emit('import')">
        <template #icon
          ><n-icon size="24"><ChannelAdd24Regular /></n-icon
        ></template>
        Import Excel
      </n-button>
      <n-button v-if="canImport" @click="emit('importDoors')">
        <template #icon
          ><n-icon size="24"><DatabaseLink20Regular /></n-icon
        ></template>
        Import DOORS
      </n-button>
      <ImportAuditHistory :allowed="canViewAudits" :project="project" />
      <n-button v-if="canCreate" @click="emit('create')">
        <template #icon
          ><n-icon size="24"><Add24Regular /></n-icon
        ></template>
        New
      </n-button>
      <n-button @click="emit('summary')">
        <template #icon
          ><n-icon size="24"><DataBarVertical24Regular /></n-icon
        ></template>
        Summary
      </n-button>
      <n-button :loading="checking" :disabled="checking" @click="emit('check')">
        <template #icon
          ><n-icon size="24"><Branch24Regular /></n-icon
        ></template>
        Check Issues
      </n-button>
      <n-text v-if="checking || progress.total" depth="3">
        Checked {{ progress.completed }}/{{ progress.total }}
      </n-text>
    </n-flex>
    <n-flex>
      <n-button ghost color="#65B25D" @click="emit('export')">
        <template #icon
          ><n-icon size="24"><DocumentArrowDown20Regular /></n-icon
        ></template>
        Export Excel
      </n-button>
    </n-flex>
  </n-flex>
  <n-flex justify="end" class="toolbar-filters">
    <n-input
      v-model:value="search"
      clearable
      placeholder="Search documents"
      aria-label="Search compliance documents"
      style="width: min(280px, 100%)"
      @keyup.enter="emit('search', search.trim())"
      @clear="emit('search', '')"
    />
    <n-select
      clearable
      placeholder="Quick filter"
      aria-label="Compliance document quick filter"
      style="width: 180px"
      :options="[{ label: 'Archived', value: 'archived' }]"
      @update:value="emit('quickFilter', $event || '')"
    />
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
    <n-button size="tiny" aria-label="Column settings" @click="emit('settings')">
      <template #icon><Settings24Regular /></template>
    </n-button>
  </n-flex>
</template>

<style scoped>
.toolbar-primary,
.toolbar-filters {
  min-width: 0;
  width: 100%;
}

.toolbar-filters {
  margin: 16px 0 4px;
}

@media (max-width: 640px) {
  .toolbar-primary,
  .toolbar-filters {
    justify-content: flex-start !important;
  }

  .toolbar-filters > :deep(*) {
    max-width: 100%;
  }
}
</style>
