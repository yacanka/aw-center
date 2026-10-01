<script setup lang="ts">
import { ref, watch } from 'vue'
import { useCompdocStatuses } from '../composables/statuses'
import {
  createCompdocStatus,
  deleteCompdocStatus,
  type CompdocStatus
} from '../api/compdocStatuses'
import { formatApiError } from '@/shared/api/apiError'

const props = defineProps<{ project: string; canManage: boolean }>()
const { statuses, loading, error, load } = useCompdocStatuses(() => props.project)
const label = ref('')
const saving = ref(false)
watch(
  () => props.project,
  () => {
    label.value = ''
  }
)

async function change(operation: () => Promise<unknown>) {
  if (!props.canManage || saving.value) return
  const project = props.project
  saving.value = true
  error.value = ''
  try {
    await operation()
    if (project !== props.project) return
    label.value = ''
    await load()
  } catch (failure) {
    if (project === props.project) {
      await load()
      error.value = formatApiError(failure)
    }
  } finally {
    saving.value = false
  }
}
function remove(item: CompdocStatus) {
  if (item.can_delete) void change(() => deleteCompdocStatus(props.project, item.id))
}
</script>

<template>
  <n-card title="Statuses" size="small">
    <n-space vertical>
      <n-text depth="3"
        >Shared by everyone in this project. Imports add new statuses automatically.</n-text
      >
      <n-alert v-if="error" type="error"
        >{{ error }} <n-button @click="load">Retry</n-button></n-alert
      >
      <n-space v-if="canManage" align="center">
        <n-input
          v-model:value="label"
          placeholder="New status name"
          aria-label="New status name"
          :maxlength="128"
          :disabled="saving"
          @keyup.enter="label.trim() && change(() => createCompdocStatus(project, label))"
        />
        <n-button
          :disabled="!label.trim() || saving || loading"
          :loading="saving"
          @click="change(() => createCompdocStatus(project, label))"
          >Add status</n-button
        >
      </n-space>
      <n-spin :show="loading">
        <n-list>
          <n-list-item v-for="item in statuses" :key="item.id">
            <n-flex justify="space-between" align="center">
              <n-space vertical :size="2">
                <n-text>{{ item.label }}</n-text>
                <n-text depth="3"
                  >{{ item.usage_count }} documents<span v-if="item.value === 'unknown'">
                    · Default status cannot be deleted</span
                  ><span v-else-if="!item.can_delete">
                    · In use, including archived documents</span
                  ></n-text
                >
              </n-space>
              <n-popconfirm v-if="canManage && item.can_delete" @positive-click="remove(item)">
                <template #trigger
                  ><n-button size="small" :disabled="saving || loading">Delete</n-button></template
                >
                Delete {{ item.label }}? Existing history will be preserved.
              </n-popconfirm>
              <n-button v-else-if="canManage" size="small" disabled>Delete</n-button>
            </n-flex>
          </n-list-item>
        </n-list>
      </n-spin>
    </n-space>
  </n-card>
</template>
