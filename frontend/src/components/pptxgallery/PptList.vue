<script setup lang="ts">
import { onMounted, h } from 'vue'
import { usePptxStore } from '@/stores/presentations'
import { NDataTable, NButton, useMessage, NSpace, type DataTableColumns } from 'naive-ui'
import type { Presentation } from '@/models/presentation'

const emits = defineEmits<{ (e: 'select', p: { id: number; title: string }): void }>()
const msg = useMessage()
const store = usePptxStore()

async function fetchList() {
  await store.fetchPresentations()
}

async function remove(id: number) {
  await store.removePresentation(id)
  msg.success('Deleted')
  fetchList()
}

async function reconvert(id: number) {
  await store.reconvertPresentation(id)
  msg.success('Reconverted')
  fetchList()
}

onMounted(fetchList)

const columns: DataTableColumns<Presentation> = [
  { title: 'Title', key: 'title' },
  { title: 'Status', key: 'status' },
  {
    title: 'Slides',
    key: 'slides',
    render(row) {
      return row.slides?.length ?? 0
    }
  },
  {
    title: 'Actions',
    key: 'actions',
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
              { size: 'small', focusable: false, tertiary: true, onClick: () => reconvert(row.id) },
              { default: () => 'Re-Convert' }
            ),
            h(
              NButton,
              { size: 'small', focusable: false, type: 'error', onClick: () => remove(row.id) },
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
  <n-data-table :columns="columns" :data="store.getPresentations" />
</template>
