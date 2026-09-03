<template>
  <n-modal v-model:show="visible" preset="dialog" title="Queue watcher reminder" centered>
    <n-space vertical>
      <n-alert type="info" :bordered="false">
        The reminder will be queued for assignees of open JIRA subtasks. Mail is delivered by the
        notification worker.
      </n-alert>
      <n-input :value="record?.issue || ''" disabled />
      <n-input-number
        v-model:value="ccbNo"
        :min="1"
        :max="999999"
        placeholder="CCB number"
        style="width: 100%"
      />
      <n-date-picker
        v-model:formatted-value="dueDate"
        type="date"
        value-format="yyyy-MM-dd"
        format="dd.MM.yyyy"
        style="width: 100%"
      />
      <n-alert v-if="errorMessage" type="error">{{ errorMessage }}</n-alert>
    </n-space>
    <template #action>
      <n-button @click="visible = false">Cancel</n-button>
      <n-button
        type="primary"
        :loading="submitting"
        :disabled="!record || !ccbNo || !dueDate"
        @click="submit"
      >
        Queue reminder
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { IDcc } from '@/features/dcc/models/dcc'
import { createDccReminder } from '@/features/dcc/api/dccRecords'
import { formatApiError } from '@/shared/api/apiError'

const visible = ref(false)
const record = ref<IDcc | null>(null)
const ccbNo = ref<number | null>(null)
const dueDate = ref<string | null>(null)
const submitting = ref(false)
const errorMessage = ref('')

function open(value: IDcc): void {
  record.value = value
  ccbNo.value = null
  dueDate.value = null
  errorMessage.value = ''
  visible.value = true
}

async function submit(): Promise<void> {
  if (!record.value || !ccbNo.value || !dueDate.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    await createDccReminder(record.value, ccbNo.value, dueDate.value)
    window.$notification.success({
      title: 'Reminder queued',
      description: 'The notification worker will deliver the watcher reminder.'
    })
    visible.value = false
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    submitting.value = false
  }
}

defineExpose({ open })
</script>
