<template>
  <n-card title="Developer / Test Data">
    <n-space vertical :size="20">
      <n-alert type="warning" title="Reset compliance documents and organization">
        Permanently delete data across all projects: documents, cover pages, local numbering
        allocations, reviews, history, import settings, notification settings, panels, people and
        compliance/organization roles. Project catalog, login accounts and DCC data are preserved.
        Numbers already issued by Numarator are not reset. Available only in development mode to
        superusers. Stop test activity and finish or cancel background jobs before resetting.
      </n-alert>
      <n-alert v-if="error" type="error">{{ error }}</n-alert>
      <n-alert v-if="completed" type="success">Test data was reset.</n-alert>
      <n-button :loading="busy" :disabled="busy" @click="loadPreview">Preview reset</n-button>
      <template v-if="preview">
        <n-table :single-line="false">
          <thead>
            <tr>
              <th>Data</th>
              <th>Records</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(count, name) in preview.counts" :key="name">
              <td>{{ name.replaceAll('_', ' ') }}</td>
              <td>{{ count }}</td>
            </tr>
          </tbody>
        </n-table>
        <n-form-item :label="`Type ${preview.confirmation_phrase} to confirm`">
          <n-input v-model:value="phrase" :disabled="busy" autocomplete="off" />
        </n-form-item>
        <n-button
          type="error"
          :loading="busy"
          :disabled="busy || phrase !== preview.confirmation_phrase"
          @click="confirmReset"
        >
          Reset compliance documents and organization
        </n-button>
      </template>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { formatApiError } from '@/shared/api/apiError'
import {
  previewTestDataReset,
  resetTestData,
  type ResetPreview
} from '@/features/tools/api/developerTestData'

const preview = ref<ResetPreview | null>(null)
const phrase = ref('')
const busy = ref(false)
const error = ref('')
const completed = ref(false)

async function loadPreview() {
  busy.value = true
  error.value = ''
  completed.value = false
  preview.value = null
  phrase.value = ''
  try {
    preview.value = await previewTestDataReset()
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    busy.value = false
  }
}

async function confirmReset() {
  if (busy.value || !preview.value || phrase.value !== preview.value.confirmation_phrase) return
  busy.value = true
  error.value = ''
  try {
    await resetTestData(preview.value, phrase.value)
    completed.value = true
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    preview.value = null
    phrase.value = ''
    busy.value = false
  }
}
</script>
