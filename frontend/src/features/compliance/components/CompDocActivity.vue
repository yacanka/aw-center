<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ICompDoc, ICompDocActivity } from '@/features/compliance/models/compdocs'
import { fetchCompdocActivity } from '@/features/compliance/api/compdocLifecycle'
import { isoToTurkishDateTime } from '@/shared/utils/time'
import { formatApiError } from '@/shared/api/apiError'

const props = defineProps<{
  show: boolean
  project: string
  document: ICompDoc
}>()
const activity = ref<ICompDocActivity[]>([])
const loading = ref(false)

watch(
  () => [props.show, props.document.id, props.document.version],
  ([show]) => {
    if (show) void loadActivity()
  },
  { immediate: true }
)

async function loadActivity() {
  if (!props.document.id) return
  loading.value = true
  try {
    activity.value = await fetchCompdocActivity(props.project, props.document.id)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    loading.value = false
  }
}

function activityContent(item: ICompDocActivity): string {
  if (item.type === 'workflow') {
    const transitionLabel = `${item.previous_status || 'Unknown'} → ${item.status}`
    return item.reason ? `${transitionLabel}: ${item.reason}` : transitionLabel
  }
  if (item.type === 'history') {
    const fields = item.changes?.map((change) => change.field).join(', ') || 'record'
    return `${item.reason || 'Document updated'} (${fields})`
  }
  return `${item.type}: ${item.status}${item.reason ? ` — ${item.reason}` : ''}`
}
</script>

<template>
  <section class="workspace-section">
    <n-spin :show="loading">
      <n-timeline v-if="activity.length">
        <n-timeline-item
          v-for="(item, index) in activity"
          :key="`${item.occurred_at}-${index}`"
          :title="item.actor || 'System'"
          :content="activityContent(item)"
          :time="isoToTurkishDateTime(item.occurred_at)"
        />
      </n-timeline>
      <n-empty v-else-if="!loading" description="No recorded activity." size="small" />
    </n-spin>
  </section>
</template>
