<script setup lang="ts">
import { ref, watch } from 'vue'
import PptUploader from '@/features/tools/components/presentations/PptUploader.vue'
import PptList from '@/features/tools/components/presentations/PptList.vue'
import PptCarousel from '@/features/tools/components/presentations/PptCarousel.vue'
import PageJobStatus from '@/features/jobs/components/PageJobStatus.vue'
import { usePageJob } from '@/features/jobs/composables/usePageJob'
import { isActiveJobStatus, type Job } from '@/features/jobs/api/jobs'
import { providePresentationController } from '@/features/tools/composables/presentationController'

const controller = providePresentationController()
const selectedId = ref<string | null>(null)
const selectedTitle = ref<string>('')
const refreshedJobs = new Set<string>()
const {
  active,
  cancel,
  cancelling,
  download,
  downloading,
  errorMessage,
  job,
  openJobCenter,
  setJob
} = usePageJob('presentation_job')

function onSelect(p: { id: string; title: string }) {
  selectedId.value = p.id
  selectedTitle.value = p.title
}

function onQueued(queuedJob: Job): void {
  setJob(queuedJob)
  void refreshGallery()
}

function onRemoved(id: string): void {
  if (selectedId.value === id) selectedId.value = null
}

watch(
  () => job.value,
  async (currentJob) => {
    if (!currentJob || isActiveJobStatus(currentJob.status) || refreshedJobs.has(currentJob.id)) {
      return
    }
    refreshedJobs.add(currentJob.id)
    await refreshGallery(currentJob.result_summary.presentation_id)
  }
)

async function refreshGallery(presentationId?: string | number): Promise<void> {
  try {
    const presentations = await controller.fetchPresentations()
    const presentation = presentations.find((item) => item.id === String(presentationId || ''))
    if (presentation) onSelect(presentation)
  } catch {
    // The domain store already presents the refresh error.
  }
}
</script>

<template>
  <n-space vertical>
    <h1>PowerPoint Gallery</h1>
    <PptUploader @queued="onQueued" />
    <n-alert v-if="errorMessage" type="error" closable @close="errorMessage = ''">
      {{ errorMessage }}
    </n-alert>
    <PageJobStatus
      :job="job"
      :cancelling="cancelling"
      :downloading="downloading"
      @cancel="cancel"
      @download="download"
      @open="openJobCenter"
    />
    <PptList
      :conversion-active="active"
      @select="onSelect"
      @queued="onQueued"
      @removed="onRemoved"
    />
    <PptCarousel v-if="selectedId" :presentation-id="selectedId" :title="selectedTitle" />
  </n-space>
</template>
