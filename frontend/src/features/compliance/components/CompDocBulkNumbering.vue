<script setup lang="ts">
import { computed, h, toRef } from 'vue'
import { NCheckbox, NText, type DataTableColumns } from 'naive-ui'
import type { ICompDoc } from '../models/compdocs'
import NumberingContextFields from './NumberingContextFields.vue'
import { useBulkNumbering } from '../composables/bulkNumbering'

const props = defineProps<{ project: string; canEdit: boolean; documents: ICompDoc[] }>()
const emit = defineEmits<{ updated: [document: unknown] }>()
const state = useBulkNumbering(
  props.project,
  toRef(props, 'canEdit'),
  (document) => emit('updated', document),
  toRef(props, 'documents')
)
const {
  visible,
  loading,
  submitting,
  refreshing,
  started,
  available,
  formats,
  format,
  error,
  rows,
  selected,
  completed,
  canSubmit
} = state
const allSelected = computed(
  () => rows.value.length > 0 && selected.value.length === rows.value.length
)
type NumberingRow = (typeof rows.value)[number]
const columns = computed<DataTableColumns<NumberingRow>>(() => [
  {
    key: 'selection',
    width: 48,
    title: () =>
      h(NCheckbox, {
        checked: allSelected.value,
        indeterminate: selected.value.length > 0 && !allSelected.value,
        disabled: started.value || !props.canEdit,
        'aria-label': 'Select all documents',
        'onUpdate:checked': (checked: boolean) => {
          rows.value.forEach((row) => {
            row.selected = checked
          })
        }
      }),
    render: (row) =>
      h(NCheckbox, {
        checked: row.selected,
        disabled: started.value || !props.canEdit,
        'aria-label': `Select ${row.document.name}`,
        'onUpdate:checked': (checked: boolean) => {
          row.selected = checked
        }
      })
  },
  { title: 'Document', key: 'document.name', minWidth: 220 },
  {
    title: 'Technical document no.',
    key: 'document.tech_doc_no',
    minWidth: 180,
    render: (row) => row.document.tech_doc_no || '—'
  },
  {
    title: 'Result',
    key: 'result',
    minWidth: 200,
    render: (row) =>
      h(
        NText,
        {
          type: row.error ? 'error' : row.allocation?.status === 'completed' ? 'success' : undefined
        },
        () => state.status(row)
      )
  }
])
defineExpose({ open: state.open })
</script>

<template>
  <n-modal
    :show="visible"
    preset="card"
    title="Assign cover page numbers"
    class="app-modal app-modal--large"
    :closable="!submitting"
    :mask-closable="!submitting"
    :close-on-esc="!submitting"
    :aria-busy="loading || submitting"
    @update:show="!$event && state.close()"
  >
    <n-space vertical size="large">
      <n-text depth="3">
        {{ project.toUpperCase() }} · Missing cover page numbers on the current table page
      </n-text>
      <n-flex v-if="loading" align="center" role="status">
        <n-spin size="small" />
        <n-text>Loading number formats…</n-text>
      </n-flex>
      <n-alert v-else-if="error" type="error" :bordered="false" role="alert">
        <n-space vertical>
          <span>{{ error }}</span>
          <n-button size="small" @click="state.load">Retry loading</n-button>
        </n-space>
      </n-alert>
      <template v-else>
        <n-tag :type="started ? 'success' : 'info'" size="small" :bordered="false" role="status">
          {{
            started
              ? `${completed} of ${selected.length} assigned`
              : `${selected.length} of ${rows.length} documents selected`
          }}
        </n-tag>
        <n-form-item label="Number format" :show-feedback="false">
          <n-select
            v-model:value="format"
            :options="formats.map((value) => ({ label: value, value }))"
            :disabled="started || !available"
            placeholder="Select a format"
            aria-label="Number format"
          />
        </n-form-item>
        <n-text depth="3">
          Applies only to selected documents on the current table page. Existing requests keep their
          original format.
        </n-text>
        <NumberingContextFields
          v-if="available && format"
          id-prefix="bulk-context"
          :fields="state.context.fields.value"
          :values="state.context.values.value"
          :loading="state.context.loading.value"
          :error="state.context.error.value"
          :disabled="started || !canEdit"
          @update:values="state.context.values.value = $event"
          @retry="state.context.load"
        />
        <n-alert v-if="!available" type="info" :bordered="false" role="status">
          Numarator is not configured for this project.
        </n-alert>
        <n-empty
          v-else-if="!rows.length"
          description="No active documents on this table page have missing cover page numbers."
        />
        <n-data-table
          v-if="rows.length"
          :columns="columns"
          :data="rows"
          :row-key="(row: NumberingRow) => row.document.id!"
          :pagination="false"
          :max-height="340"
          :scroll-x="648"
          size="small"
          aria-label="Documents to number"
        />
        <n-text v-if="started" depth="3" role="status">
          {{
            submitting
              ? 'Submitting requests…'
              : 'Queued requests continue in the background. Reopen a document to recover an unfinished request.'
          }}
        </n-text>
        <n-text v-else depth="3">
          Each selected document receives its own number. Existing numbers are preserved.
        </n-text>
      </template>
    </n-space>
    <template #footer>
      <n-space justify="end">
        <n-button :disabled="submitting" @click="state.close">Close</n-button>
        <template v-if="!loading && !error">
          <n-button
            v-if="started && completed === selected.length"
            :disabled="submitting || refreshing"
            @click="state.chooseMore"
            >Choose more documents</n-button
          >
          <n-button
            v-if="started"
            :loading="refreshing"
            :disabled="submitting || refreshing"
            @click="state.refresh"
            >Refresh results</n-button
          >
          <n-button
            type="primary"
            :loading="submitting"
            :disabled="!canSubmit"
            @click="state.submit"
          >
            {{
              submitting
                ? 'Submitting…'
                : started
                  ? 'Retry unfinished'
                  : `Assign ${selected.length} numbers`
            }}
          </n-button>
        </template>
      </n-space>
    </template>
  </n-modal>
</template>
