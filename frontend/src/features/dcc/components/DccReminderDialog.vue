<template>
  <n-modal
    v-model:show="visible"
    preset="dialog"
    title="Send a reminder"
    centered
    :mask-closable="!submitting"
    :closable="!submitting"
    :close-on-esc="!submitting"
  >
    <n-space vertical>
      <n-alert type="info" :bordered="false">
        Assignees of unfinished JIRA subtasks receive this reminder. Completed subtasks are
        excluded.
      </n-alert>
      <n-text strong>{{ record?.issue }} · {{ record?.title }}</n-text>
      <n-form-item label="CCB number">
        <n-input-number
          v-model:value="ccbNo"
          :min="1"
          :max="999999"
          placeholder="CCB number"
          :disabled="submitting"
          :input-props="{ 'aria-label': 'CCB number' }"
          style="width: 100%"
        />
      </n-form-item>
      <n-form-item label="Response due date">
        <n-date-picker
          v-model:formatted-value="dueDate"
          type="date"
          :disabled="submitting"
          :input-props="{ 'aria-label': 'Response due date' }"
          value-format="yyyy-MM-dd"
          format="dd.MM.yyyy"
          style="width: 100%"
        />
      </n-form-item>
      <n-text depth="2">One reminder per issue can be queued each hour.</n-text>
      <n-alert v-if="errorMessage" role="alert" type="error">{{ errorMessage }}</n-alert>
    </n-space>
    <template #action>
      <n-button :disabled="submitting" @click="visible = false">Cancel</n-button>
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
  if (submitting.value || !record.value || !ccbNo.value || !dueDate.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    await createDccReminder(record.value, ccbNo.value, dueDate.value)
    window.$message.success(`Reminder queued for ${record.value.issue}.`, {
      duration: 3000,
      closable: true
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
