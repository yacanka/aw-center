<script setup lang="ts">
import { onMounted, h } from 'vue'
import { usePresentationController } from '@/features/tools/composables/presentationController'
import { NDataTable, NButton, useMessage, NSpace, type DataTableColumns } from 'naive-ui'
import type { Presentation } from '@/features/tools/models/presentation'
import type { Job } from '@/features/jobs/api/jobs'

const emits = defineEmits<{
  select: [presentation: { id: string; title: string }]
  queued: [job: Job]
  removed: [id: string]
}>()
const props = defineProps<{ conversionActive: boolean }>()
const msg = useMessage()
const controller = usePresentationController()
const reconvertAttempts = new Map<string, string>()

async function fetchList() {
  try {
    await controller.fetchPresentations()
  } catch {
    // The domain store already presents the API error.
  }
}

async function remove(id: string) {
  try {
    await controller.removePresentation(id)
    emits('removed', id)
    msg.success('Deleted')
  } catch {
    // The domain store already presents the API error.
  }
}

async function reconvert(id: string) {
  const idempotencyKey = reconvertAttempts.get(id) || crypto.randomUUID()
  reconvertAttempts.set(id, idempotencyKey)
  try {
    const job = await controller.reconvertPresentation(id, idempotencyKey)
    reconvertAttempts.delete(id)
    emits('queued', job)
    msg.success('Reconversion queued.')
  } catch {
    // Keep the key so retrying the same intent replays instead of duplicating the job.
  }
}

onMounted(fetchList)

const columns: DataTableColumns<Presentation> = [
  { title: 'Title', key: 'title', minWidth: 220 },
  { title: 'Status', key: 'status', width: 120 },
  {
    title: 'Slides',
    key: 'slides',
    width: 90,
    render(row) {
      return row.slides?.length ?? 0
    }
  },
  {
    title: 'Actions',
    key: 'actions',
    width: 300,
    render(row) {
      return h(
        NSpace,
        {},
        {
          default: () => [
            h(
              NButton,
              {
                size: 'small',
                focusable: false,
                onClick: () => emits('select', { id: row.id, title: row.title })
              },
              { default: () => 'Show' }
            ),
            h(
              NButton,
              {
                size: 'small',
                focusable: false,
                tertiary: true,
                disabled: props.conversionActive || ['pending', 'converting'].includes(row.status),
                onClick: () => reconvert(row.id)
              },
              { default: () => 'Re-Convert' }
            ),
            h(
              NButton,
              {
                size: 'small',
                focusable: false,
                type: 'error',
                disabled: props.conversionActive || ['pending', 'converting'].includes(row.status),
                onClick: () => remove(row.id)
              },
              { default: () => 'Delete' }
            )
          ]
        }
      )
    }
  }
]
</script>

<template>
  <n-data-table :columns="columns" :data="controller.presentations.value" :scroll-x="730" />
</template>
