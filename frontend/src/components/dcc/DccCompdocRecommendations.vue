<template>
  <n-card v-if="available" title="Suggested Compliance Documents" size="small">
    <n-space vertical>
      <n-alert type="info" :bordered="false">
        Suggestions are deterministic and evidence-based. Nothing is linked until you select records
        and create a new immutable preview.
      </n-alert>
      <n-empty v-if="!recommendations.length" description="No strong CompDoc match was found." />
      <n-list v-else bordered>
        <n-list-item v-for="item in recommendations" :key="item.id">
          <n-space justify="space-between" align="start" :wrap="false">
            <n-space vertical size="small">
              <n-space align="center">
                <n-text strong>{{ item.name }}</n-text>
                <n-tag type="info" size="small">{{ item.score }}% match</n-tag>
                <n-tag v-if="item.status" size="small">{{ statusLabel(item.status) }}</n-tag>
              </n-space>
              <n-text depth="3">
                {{ item.panel || 'No panel' }} · {{ item.ata || 'No ATA' }}
              </n-text>
              <n-text v-for="reason in item.reasons" :key="reason" depth="3">
                {{ reason }}
              </n-text>
            </n-space>
            <n-switch
              :value="selectedIds.includes(item.id)"
              :aria-label="`Select ${item.name}`"
              @update:value="toggleSelection(item.id, $event)"
            />
          </n-space>
        </n-list-item>
      </n-list>
      <n-alert v-if="candidatesTruncated" type="warning" :bordered="false">
        The recommendation scan reached its bounded candidate limit. Use Compliance Documents for a
        wider manual selection if needed.
      </n-alert>
      <n-alert v-if="errorMessage" type="error" closable @close="errorMessage = ''">
        {{ errorMessage }}
      </n-alert>
      <n-space v-if="recommendations.length" justify="end">
        <n-button
          type="primary"
          secondary
          :loading="applying"
          :disabled="!selectedIds.length"
          @click="applySelection"
        >
          Create enriched preview ({{ selectedIds.length }})
        </n-button>
      </n-space>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { formatApiError } from '@/services/apiError'
import { applyDccCompdocRecommendations } from '@/services/dccJobs'
import type { DccCompdocRecommendation } from '@/services/jobSummaries'
import type { Job } from '@/services/jobs'

const props = defineProps<{
  jobId: string
  available: boolean
  recommendations: DccCompdocRecommendation[]
  candidatesTruncated: boolean
}>()
const emit = defineEmits<{ created: [job: Job] }>()
const selectedIds = ref<string[]>([])
const applying = ref(false)
const errorMessage = ref('')

watch(
  () => props.jobId,
  () => (selectedIds.value = [])
)

function toggleSelection(documentId: string, selected: boolean): void {
  selectedIds.value = selected
    ? [...new Set([...selectedIds.value, documentId])]
    : selectedIds.value.filter((value) => value != documentId)
}

async function applySelection(): Promise<void> {
  if (!selectedIds.value.length) return
  applying.value = true
  errorMessage.value = ''
  try {
    const job = await applyDccCompdocRecommendations(props.jobId, selectedIds.value)
    emit('created', job)
    window.$notification.success({
      title: 'Enriched preview ready',
      description: 'The same JIRA snapshot now includes your selected CompDoc sources.'
    })
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    applying.value = false
  }
}

function statusLabel(status: string): string {
  return status.replaceAll('_', ' ')
}
</script>
