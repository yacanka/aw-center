<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ICompDoc } from '@/models/compdocs'
import { statusOptions } from '@/services/compdocCatalog'
import {
  bulkUpdateCompdocs,
  exportSelectedCompdocs,
  fetchCompdocAssignees,
  type CompdocAssignees
} from '@/services/compdocLifecycle'
import { formatApiError } from '@/services/apiError'

const props = defineProps<{
  project: string
  documents: ICompDoc[]
  canChange: boolean
  canDelete: boolean
}>()
const emit = defineEmits<{ completed: [] }>()
const action = ref<'work' | 'transition' | 'archive' | 'restore' | 'export'>('work')
const reason = ref('')
const status = ref('unknown')
const owner = ref<number | null>(null)
const ownerGroup = ref<number | null>(null)
const dueDate = ref<string | null>(null)
const loading = ref(false)
const assignees = ref<CompdocAssignees>({ users: [], groups: [] })
const versioned = computed(() =>
  props.documents
    .filter((item) => item.id && item.source_history_id)
    .map((item) => ({ id: item.id!, source_history_id: item.source_history_id! }))
)

watch(
  action,
  (value) => {
    if (value === 'work' && props.canChange && !assignees.value.users.length) {
      void loadAssignees()
    }
  },
  { immediate: true }
)

async function loadAssignees() {
  try {
    assignees.value = await fetchCompdocAssignees(props.project)
  } catch (error) {
    window.$message.error(formatApiError(error))
  }
}

async function apply() {
  loading.value = true
  try {
    if (action.value === 'export') await downloadSelection()
    else {
      await bulkUpdateCompdocs(
        props.project,
        versioned.value,
        action.value,
        reason.value,
        actionValues()
      )
      window.$message.success(`${versioned.value.length} documents updated.`)
    }
    emit('completed')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    loading.value = false
  }
}

function actionValues(): Record<string, unknown> {
  if (action.value === 'transition') {
    return {
      status: status.value,
      effective_date: new Date().toISOString().slice(0, 10),
      next_action_due_date: dueDate.value
    }
  }
  if (action.value === 'work') {
    return {
      owner: owner.value,
      owner_group: ownerGroup.value,
      next_action_due_date: dueDate.value
    }
  }
  return {}
}

async function downloadSelection() {
  const blob = await exportSelectedCompdocs(props.project, versioned.value)
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${props.project.toUpperCase()} Selected Compliance Documents.xlsx`
  anchor.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <n-card size="small" embedded>
    <n-flex align="center">
      <n-text strong>{{ documents.length }} selected</n-text>
      <n-select
        v-model:value="action"
        style="width: 170px"
        :options="[
          { label: 'Assign work', value: 'work', disabled: !canChange },
          { label: 'Transition', value: 'transition', disabled: !canChange },
          { label: 'Archive', value: 'archive', disabled: !canDelete },
          { label: 'Restore', value: 'restore', disabled: !canChange || !canDelete },
          { label: 'Export selection', value: 'export' }
        ]"
      />
      <n-select
        v-if="action === 'transition'"
        v-model:value="status"
        style="width: 180px"
        :options="statusOptions"
      />
      <n-select
        v-if="action === 'work'"
        v-model:value="owner"
        clearable
        placeholder="Owner"
        style="width: 160px"
        :options="assignees.users.map((item) => ({ label: item.username, value: item.id }))"
      />
      <n-select
        v-if="action === 'work'"
        v-model:value="ownerGroup"
        clearable
        placeholder="Team"
        style="width: 150px"
        :options="assignees.groups.map((item) => ({ label: item.name, value: item.id }))"
      />
      <n-date-picker
        v-if="action === 'work' || action === 'transition'"
        v-model:formatted-value="dueDate"
        type="date"
        clearable
      />
      <n-input
        v-if="action !== 'export'"
        v-model:value="reason"
        placeholder="Reason (optional)"
        maxlength="255"
        style="min-width: 220px; flex: 1"
      />
      <n-button type="primary" :loading="loading" @click="apply">Apply</n-button>
    </n-flex>
  </n-card>
</template>
