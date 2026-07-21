<script setup lang="ts">
import { computed } from 'vue'
import type { IColumnSetting, ICompDocFieldMetadata } from '@/models/compdocs'

const props = defineProps<{ fields: ICompDocFieldMetadata[] }>()
const emit = defineEmits<{
  apply: []
  reset: []
  default: []
  all: []
}>()
const show = defineModel<boolean>('show', { required: true })
const settings = defineModel<IColumnSetting[]>('settings', { required: true })
const fieldsByKey = computed(() => new Map(props.fields.map((field) => [field.key, field])))

function fieldOptions(currentKey: string) {
  const selected = new Set(settings.value.map((setting) => setting.key))
  return props.fields.map((field) => ({
    label: field.label,
    value: field.key,
    disabled: field.key !== currentKey && selected.has(field.key)
  }))
}

function field(key: string) {
  return fieldsByKey.value.get(key)
}

function toggle(setting: IColumnSetting, key: 'sorter' | 'filter' | 'ellipsis') {
  setting[key] = !setting[key]
}

function createSetting(): IColumnSetting {
  const available = props.fields.find(
    (candidate) => !settings.value.some((setting) => setting.key === candidate.key)
  )
  return {
    key: available?.key || '',
    width: available?.width || 160,
    sorter: Boolean(available?.sortable),
    filter: Boolean(available && available.filter_kind !== 'none'),
    ellipsis: Boolean(available?.ellipsis)
  }
}
</script>

<template>
  <n-modal v-model:show="show" preset="card" title="Column Settings" style="width: 920px">
    <n-alert type="info" :bordered="false" style="margin-bottom: 12px">
      Columns and capabilities are validated against the active project's server schema.
    </n-alert>
    <n-scrollbar style="max-height: 600px; padding-right: 16px">
      <n-dynamic-input
        v-model:value="settings"
        show-sort-button
        :min="1"
        :on-create="createSetting"
      >
        <template #default="{ value }">
          <n-grid cols="40" x-gap="12" style="align-items: center">
            <n-grid-item span="13">
              <n-select
                v-model:value="value.key"
                :options="fieldOptions(value.key)"
                placeholder="Select Column"
              />
            </n-grid-item>
            <n-grid-item span="7">
              <n-input-number v-model:value="value.width" :min="60" :max="600" />
            </n-grid-item>
            <n-grid-item span="5">
              <n-tag size="small">{{ field(value.key)?.filter_kind || 'none' }}</n-tag>
            </n-grid-item>
            <n-grid-item span="5">
              <n-button
                block
                :disabled="!field(value.key)?.sortable"
                :type="value.sorter ? 'success' : 'default'"
                @click="toggle(value, 'sorter')"
              >
                Sorter
              </n-button>
            </n-grid-item>
            <n-grid-item span="5">
              <n-button
                block
                :disabled="field(value.key)?.filter_kind === 'none'"
                :type="value.filter ? 'success' : 'default'"
                @click="toggle(value, 'filter')"
              >
                Filter
              </n-button>
            </n-grid-item>
            <n-grid-item span="5">
              <n-button
                block
                :type="value.ellipsis ? 'success' : 'default'"
                @click="toggle(value, 'ellipsis')"
              >
                Tooltip
              </n-button>
            </n-grid-item>
          </n-grid>
        </template>
      </n-dynamic-input>
    </n-scrollbar>
    <n-flex justify="space-between" style="margin-top: 16px">
      <n-space>
        <n-button @click="emit('default')">Recommended</n-button>
        <n-button @click="emit('all')">All Fields</n-button>
      </n-space>
      <n-space>
        <n-button type="error" secondary @click="emit('reset')">Reset</n-button>
        <n-button type="primary" @click="emit('apply')">Apply</n-button>
      </n-space>
    </n-flex>
  </n-modal>
</template>
