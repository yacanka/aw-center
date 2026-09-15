<template>
  <n-card title="Developer / Test Data">
    <n-space vertical :size="20">
      <n-alert type="warning" title="Reset compliance documents and organization">
        Permanently delete data across all projects: documents, cover pages, local numbering
        allocations, reviews, history, import settings, notification settings, panels, people and
        compliance/organization roles. Project catalog, login accounts and DCC data are preserved.
        Numbers already issued by Numarator are not reset. Available only in development mode to
        superusers. Preparation pauses compliance and organization writes and requests cancellation
        of related jobs. It remains active until you release it or complete the reset.
      </n-alert>
      <n-alert v-if="error" type="error">{{ error }}</n-alert>
      <n-alert v-if="completed" type="success">Test data was reset.</n-alert>
      <n-button :loading="busy" :disabled="busy" @click="loadPreview">Preview reset</n-button>
      <template v-if="preview">
        <n-alert :type="preview.ready ? 'success' : 'info'">
          {{
            preview.ready
              ? 'Ready to reset. Review the counts below.'
              : preview.prepared
                ? 'Preparation is active. Refresh the preview after running work finishes.'
                : 'Prepare the reset to pause writes and cancel related jobs.'
          }}
        </n-alert>
        <n-space>
          <n-button :disabled="busy" @click="prepareReset">
            {{ preview.prepared ? 'Check cancellations again' : 'Prepare and cancel related jobs' }}
          </n-button>
          <n-button v-if="preview.prepared" :disabled="busy" @click="releaseReset">
            Release preparation
          </n-button>
        </n-space>
        <n-alert
          v-if="preview.blockers.job_count"
          type="warning"
          title="Jobs must finish cancelling"
        >
          {{ preview.blockers.job_count }} related jobs. Showing up to 100.
          <ul>
            <li v-for="job in preview.blockers.jobs" :key="job.id">
              {{ job.id }} — {{ job.status }}
            </li>
          </ul>
        </n-alert>
        <n-alert
          v-if="preview.blockers.allocation_count || preview.blockers.uncertain_job_count"
          type="warning"
          title="Number allocations need attention"
        >
          {{ preview.blockers.allocation_count }} incomplete allocations;
          {{ preview.blockers.uncertain_job_count }} jobs with an uncertain external outcome.
          Release preparation and resolve these through the existing numbering flow before preparing
          again. Issued numbers remain in Numarator. Showing up to 100 of each.
          <ul>
            <li v-for="allocation in preview.blockers.allocations" :key="allocation.id">
              {{ allocation.project__slug }} — {{ allocation.id }} — {{ allocation.status }}
            </li>
            <li v-for="job in preview.blockers.uncertain_jobs" :key="job.id">
              {{ job.id }} — {{ job.status }}
            </li>
          </ul>
        </n-alert>
        <n-alert v-if="preview.blockers.notification_count" type="warning">
          {{ preview.blockers.notification_count }} compliance notifications are already claimed.
          Wait for delivery to finish. If the notification worker stopped, release preparation and
          restart it to recover its claims, then prepare again.
        </n-alert>
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
          :disabled="busy || !preview.ready || phrase !== preview.confirmation_phrase"
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
  prepareTestDataReset,
  releaseTestDataReset,
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

async function updatePreparation(action: typeof prepareTestDataReset) {
  if (busy.value || !preview.value) return
  busy.value = true
  error.value = ''
  phrase.value = ''
  try {
    preview.value = await action(preview.value)
  } catch (cause) {
    error.value = formatApiError(cause)
    preview.value = null
  } finally {
    busy.value = false
  }
}

function prepareReset() {
  return updatePreparation(prepareTestDataReset)
}

function releaseReset() {
  return updatePreparation(releaseTestDataReset)
}

async function confirmReset() {
  if (busy.value || !preview.value?.ready || phrase.value !== preview.value.confirmation_phrase)
    return
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
