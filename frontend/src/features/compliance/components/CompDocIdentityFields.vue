<template>
  <n-card title="Identity" size="small">
    <n-grid responsive="self" item-responsive :x-gap="12" :y-gap="4" :cols="48">
      <n-form-item-gi
        v-if="showNumberSource && numberingAvailable"
        span="48"
        label="Cover page number source"
        class="number-source"
      >
        <n-radio-group
          :value="numberSource"
          name="cover-page-number-source"
          :disabled="readonly"
          @update:value="updateNumberSource"
        >
          <n-radio-button value="manual">Enter manually</n-radio-button>
          <n-radio-button value="numarator">Create with Numarator</n-radio-button>
        </n-radio-group>
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:12" path="panel" label="Panel">
        <n-select
          v-model:value="compdoc.panel"
          placeholder="Select Panel"
          :options="panelOptions"
          :disabled="readonly"
          clearable
          :status="changed('panel')"
          @update:value="syncAtaFromPanel"
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:8" path="ata" label="ATA">
        <n-input :value="compdoc.ata || ''" placeholder="—" readonly />
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:28" path="name" label="Name">
        <n-input
          v-model:value="compdoc.name"
          maxlength="256"
          :readonly="readonly"
          :status="changed('name')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:20" path="signature_panel" label="Signature Panel">
        <n-select
          v-model:value="compdoc.signature_panel"
          :options="store.getSignaturePanelOptions"
          multiple
          max-tag-count="responsive"
          :disabled="readonly"
          :status="arrayChanged ? 'warning' : ''"
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:20" path="cover_page_no" label="Cover Page No">
        <n-input
          v-model:value="compdoc.cover_page_no"
          maxlength="32"
          :readonly="readonly || numberSource === 'numarator'"
          :placeholder="numberSource === 'numarator' ? 'Assigned after save' : undefined"
          :status="changed('cover_page_no')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:8" path="cover_page_issue" label="Issue">
        <n-input
          v-model:value="compdoc.cover_page_issue"
          maxlength="255"
          :readonly="readonly"
          :status="changed('cover_page_issue')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
    </n-grid>
  </n-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { useCompdocController } from '@/features/compliance/composables/compdocController'
import { checkArrayEquals } from '@/shared/utils/array'

const props = defineProps<{
  compdoc: ICompDoc
  original: ICompDoc
  readonly: boolean
  showNumberSource?: boolean
  numberingAvailable?: boolean
  numberSource?: 'manual' | 'numarator'
}>()
const emit = defineEmits<{
  'update:numberSource': [value: 'manual' | 'numarator']
}>()
const store = useCompdocController()
const panelOptions = computed(() => {
  const options = store.getPanelOptions
  const selectedPanel = props.compdoc.panel
  if (selectedPanel === null || options.some((option) => option.value === selectedPanel)) {
    return options
  }
  if (!props.compdoc.panel_name) return options
  const ata = props.compdoc.ata ? ` · ATA ${props.compdoc.ata}` : ''
  return [...options, { label: `${props.compdoc.panel_name}${ata}`, value: selectedPanel }]
})
const arrayChanged = computed(
  () => !checkArrayEquals(props.original.signature_panel, props.compdoc.signature_panel)
)
function changed(field: keyof ICompDoc): '' | 'warning' {
  return props.original[field] === props.compdoc[field] ? '' : 'warning'
}

function syncAtaFromPanel(panelId: number | null): void {
  const options = optionsForPanel(panelId)
  props.compdoc.ata = options.length === 1 ? String(options[0].value) : null
}

function optionsForPanel(panelId: number | null) {
  if (!panelId) return []
  return store.getPanels
    .filter((panel) => panel.id === panelId)
    .sort((left, right) => left.ata.localeCompare(right.ata))
    .map((panel) => ({ label: panel.ata, value: panel.ata }))
}

function updateNumberSource(value: 'manual' | 'numarator'): void {
  emit('update:numberSource', value)
}
</script>

<style scoped>
.number-source :deep(.n-form-item-blank) {
  border-top: 1px solid var(--n-border-color);
  padding-top: 10px;
}
</style>
