<template>
  <n-space vertical size="large">
    <n-alert :type="inspection.matching.requires_input ? 'warning' : 'info'" :bordered="false">
      {{ inspection.matching.reason }}
      <template v-if="inspection.matching.keys.length">
        Suggested identity:
        {{ inspection.matching.keys.map((index) => inspection.first.columns[index]).join(' + ') }}.
      </template>
    </n-alert>
    <div class="table-pair">
      <n-card
        v-for="side in sides"
        :key="side"
        :title="side === 'first' ? 'Old table' : 'New table'"
        size="small"
        embedded
      >
        <n-form label-placement="top" :disabled="disabled">
          <n-form-item label="Worksheet">
            <n-select
              :value="selection[side]?.sheet"
              :options="sheetOptions(side)"
              @update:value="changeSheet(side, $event)"
            />
          </n-form-item>
          <n-form-item label="Header row">
            <n-select
              :value="selection[side]?.header_row"
              :options="headerOptions(side)"
              @update:value="changeHeader(side, $event)"
            />
          </n-form-item>
        </n-form>
        <n-text depth="3"
          >Last inspected preview · {{ inspection[side].row_count }} data rows</n-text
        >
        <n-data-table
          :columns="previewColumns(side)"
          :data="previewRows(side)"
          :scroll-x="inspection[side].columns.length * 150"
          size="small"
        />
      </n-card>
    </div>
    <n-alert v-if="tableChanged" type="info" :bordered="false">
      Inspect again to update columns and matching suggestions for the selected table.
    </n-alert>
    <template v-else>
      <n-collapse>
        <n-collapse-item title="Column mapping" name="columns">
          <n-text depth="3"
            >Map renamed columns here. Unmapped columns are reported as added or removed.</n-text
          >
          <div class="column-mappings">
            <n-form-item
              v-for="(label, index) in inspection.first.columns"
              :key="index"
              :label="label"
            >
              <n-select
                :value="mappedColumn(index)"
                :options="columnOptions"
                clearable
                :disabled="disabled"
                placeholder="Removed column"
                @update:value="mapColumn(index, $event)"
              />
            </n-form-item>
          </div>
        </n-collapse-item>
      </n-collapse>
      <n-form label-placement="top" :disabled="disabled">
        <n-form-item label="Match rows using">
          <n-select
            :value="selection.matching?.mode || 'auto'"
            :options="matchingOptions"
            @update:value="setMode"
          />
        </n-form-item>
        <n-form-item
          v-if="selection.matching?.mode === 'keys'"
          label="Identity columns (choose up to three)"
        >
          <n-select
            multiple
            :max="3"
            :value="selection.matching.keys || []"
            :options="identityOptions"
            @update:value="setKeys"
          />
        </n-form-item>
        <n-alert v-if="selection.matching?.mode === 'position'" type="warning" :bordered="false">
          Row-order matching pairs the first data row with the first, and so on. Moved rows may
          appear as changes.
        </n-alert>
      </n-form>
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ComparisonInspection, ExcelSelection } from '@/features/tools/api/unifiedComparison'
const props = defineProps<{
  inspection: ComparisonInspection
  selection: ExcelSelection
  disabled: boolean
}>()
const emit = defineEmits<{ update: [selection: ExcelSelection] }>()
const sides = ['first', 'second'] as const
type Side = (typeof sides)[number]
const matchingOptions = [
  { label: 'Automatic suggestion', value: 'auto' },
  { label: 'Identity columns', value: 'keys' },
  { label: 'Row order', value: 'position' }
]
const columnOptions = computed(() =>
  props.inspection.second.columns.map((label, value) => ({ label, value }))
)
const identityOptions = computed(() =>
  (props.selection.columns || []).map(([value]) => ({
    label: props.inspection.first.columns[value],
    value
  }))
)
const tableChanged = computed(() =>
  sides.some(
    (side) =>
      props.selection[side]?.sheet !== props.inspection[side].selected.sheet ||
      props.selection[side]?.header_row !== props.inspection[side].selected.header_row
  )
)
function sheetOptions(side: Side) {
  return props.inspection[side].sheets.map((sheet) => ({ label: sheet.name, value: sheet.name }))
}
function headerOptions(side: Side) {
  const sheet = props.inspection[side].sheets.find(
    (item) => item.name === props.selection[side]?.sheet
  )
  return (sheet?.headers || []).map((header) => ({
    label: `Row ${header.row}: ${header.labels.filter(Boolean).join(' · ').slice(0, 100)}`,
    value: header.row
  }))
}
function changeSheet(side: Side, name: string) {
  emit('update', {
    ...props.selection,
    [side]: { sheet: name },
    columns: undefined,
    matching: { mode: 'auto' }
  })
}
function changeHeader(side: Side, row: number) {
  emit('update', {
    ...props.selection,
    [side]: { ...props.selection[side]!, header_row: row },
    columns: undefined,
    matching: { mode: 'auto' }
  })
}
function mappedColumn(index: number) {
  return props.selection.columns?.find((pair) => pair[0] === index)?.[1] ?? null
}
function mapColumn(index: number, target: number | null) {
  const columns = (props.selection.columns || []).filter(
    (pair) => pair[0] !== index && pair[1] !== target
  )
  if (target !== null) columns.push([index, target])
  emit('update', { ...props.selection, columns, matching: { mode: 'auto' } })
}
function setMode(mode: 'auto' | 'keys' | 'position') {
  emit('update', { ...props.selection, matching: { mode, keys: [] } })
}
function setKeys(keys: number[]) {
  emit('update', { ...props.selection, matching: { mode: 'keys', keys } })
}
function previewColumns(side: Side) {
  return props.inspection[side].columns.map((title, index) => ({
    title,
    key: String(index),
    width: 150,
    ellipsis: { tooltip: true }
  }))
}
function previewRows(side: Side) {
  return props.inspection[side].preview.map((row, key) => ({
    key,
    ...Object.fromEntries(row.map((value, index) => [String(index), value]))
  }))
}
</script>

<style scoped>
.table-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.table-pair > * {
  min-width: 0;
}
.column-mappings {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr));
  gap: 12px;
  margin-top: 16px;
}
@media (max-width: 900px) {
  .table-pair {
    grid-template-columns: 1fr;
  }
}
</style>
