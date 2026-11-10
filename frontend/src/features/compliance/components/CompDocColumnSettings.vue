<script setup lang="ts">
import { computed, ref } from 'vue'
import { useThemeVars } from 'naive-ui'
import type { IColumnSetting, ICompDocFieldMetadata } from '@/features/compliance/models/compdocs'
import { createAllColumnSettings } from '@/features/compliance/api/compdocColumns'

const props = defineProps<{ fields: ICompDocFieldMetadata[] }>()
const settings = defineModel<IColumnSetting[]>('settings', { required: true })
const theme = useThemeVars()
const search = ref('')
const fieldsByKey = computed(() => new Map(props.fields.map((field) => [field.key, field])))
const available = computed(() =>
  props.fields
    .filter((field) => !settings.value.some((item) => item.key === field.key))
    .map((field) => ({ label: field.label, value: field.key }))
)
const visible = computed(() =>
  settings.value.filter((item) =>
    fieldsByKey.value.get(item.key)?.label.toLowerCase().includes(search.value.toLowerCase())
  )
)
function add(key: string) {
  const field = props.fields.find((field) => field.key === key)
  if (field) settings.value = [...settings.value, ...createAllColumnSettings([field])]
}
function move(key: string, offset: number) {
  const next = [...settings.value]
  const index = next.findIndex((item) => item.key === key)
  const target = index + offset
  if (target < 0 || target >= next.length) return
  ;[next[index], next[target]] = [next[target], next[index]]
  settings.value = next
}
</script>

<template>
  <section class="column-editor">
    <n-flex class="column-tools">
      <n-input
        v-model:value="search"
        clearable
        placeholder="Find a selected column"
        aria-label="Find a selected column"
      />
      <n-select
        :value="null"
        :options="available"
        filterable
        :disabled="!available.length"
        placeholder="Add a column"
        aria-label="Add a column"
        @update:value="add"
      />
    </n-flex>
    <n-text depth="3"
      >{{ settings.length }} columns selected. Use Move up and Move down to change their
      order.</n-text
    >
    <n-empty v-if="!visible.length" description="No matching columns" />
    <article
      v-for="setting in visible"
      :key="setting.key"
      class="column-row"
      :aria-label="fieldsByKey.get(setting.key)?.label"
    >
      <div class="column-heading">
        <strong>{{ fieldsByKey.get(setting.key)?.label }}</strong>
        <n-space :size="6">
          <n-button
            size="small"
            :aria-label="`Move ${fieldsByKey.get(setting.key)?.label} up`"
            :disabled="settings[0]?.key === setting.key"
            @click="move(setting.key, -1)"
            >Move up</n-button
          >
          <n-button
            size="small"
            :aria-label="`Move ${fieldsByKey.get(setting.key)?.label} down`"
            :disabled="settings[settings.length - 1]?.key === setting.key"
            @click="move(setting.key, 1)"
            >Move down</n-button
          >
          <n-button
            size="small"
            :aria-label="`Remove ${fieldsByKey.get(setting.key)?.label}`"
            :disabled="settings.length === 1"
            @click="settings = settings.filter((item) => item.key !== setting.key)"
            >Remove</n-button
          >
        </n-space>
      </div>
      <div class="column-controls">
        <div>
          <n-text depth="3">Width (px)</n-text
          ><n-input-number
            v-model:value="setting.width"
            :aria-label="`${fieldsByKey.get(setting.key)?.label} width`"
            :min="60"
            :max="600"
          />
        </div>
        <n-checkbox
          v-model:checked="setting.sorter"
          :disabled="!fieldsByKey.get(setting.key)?.sortable"
          >Enable sorting</n-checkbox
        >
        <n-checkbox
          v-model:checked="setting.filter"
          :disabled="fieldsByKey.get(setting.key)?.filter_kind === 'none'"
          >Enable filtering</n-checkbox
        >
        <n-checkbox v-model:checked="setting.ellipsis">Truncate with tooltip</n-checkbox>
      </div>
    </article>
  </section>
</template>

<style scoped>
.column-editor {
  display: grid;
  gap: 16px;
  min-width: 0;
}
.column-tools > * {
  flex: 1 1 220px;
  min-width: 0;
}
.column-row {
  padding: 16px;
  border: 1px solid v-bind('theme.borderColor');
  border-radius: v-bind('theme.borderRadius');
  background: v-bind('theme.cardColor');
}
.column-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}
.column-controls {
  display: grid;
  grid-template-columns: 150px repeat(3, minmax(0, 1fr));
  align-items: center;
  gap: 16px;
}
@media (max-width: 760px) {
  .column-controls {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 440px) {
  .column-controls {
    grid-template-columns: 1fr;
  }
}
</style>
