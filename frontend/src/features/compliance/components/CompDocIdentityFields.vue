<template>
  <n-card title="Identity" size="small">
    <n-grid responsive="self" item-responsive :x-gap="12" :y-gap="4" :cols="12">
      <n-form-item-gi
        v-if="showNumberSource && numberingAvailable"
        span="12"
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
      <n-form-item-gi span="0:12 700:3" path="panel" label="Panel">
        <n-select
          :value="selectedPanelName"
          placeholder="Select Panel"
          :options="panelOptions"
          :disabled="readonly"
          clearable
          :status="changed('panel')"
          @update:value="selectPanel"
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:12 700:2" path="ata" label="ATA">
        <n-select
          :value="compdoc.ata"
          placeholder="Select ATA"
          :options="ataOptions"
          :disabled="readonly || !selectedPanelName"
          clearable
          :status="changed('ata')"
          @update:value="selectAta"
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:12 700:7" path="name" label="Name">
        <n-input
          v-model:value="compdoc.name"
          maxlength="256"
          :readonly="readonly"
          :status="changed('name')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:12 700:5" path="signature_panel" label="Signature Panel">
        <n-select
          v-model:value="compdoc.signature_panel"
          :options="store.getSignaturePanelOptions"
          multiple
          max-tag-count="responsive"
          :disabled="readonly"
          :status="arrayChanged ? 'warning' : ''"
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:12 700:5" path="cover_page_no" label="Cover Page No">
        <n-input
          v-model:value="compdoc.cover_page_no"
          maxlength="32"
          :readonly="readonly || numberSource === 'numarator'"
          :placeholder="numberSource === 'numarator' ? 'Assigned after save' : undefined"
          :status="changed('cover_page_no')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:12 700:2" path="cover_page_issue" label="Issue">
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
const selectedPanelName = computed(
  () =>
    props.compdoc.panel_name ||
    store.getPanels.find((panel) => panel.id === props.compdoc.panel)?.name ||
    null
)
const panelOptions = computed(() => {
  const names = new Set(store.getPanels.map((panel) => panel.name))
  if (selectedPanelName.value) names.add(selectedPanelName.value)
  return [...names]
    .sort((left, right) => left.localeCompare(right))
    .map((name) => ({ label: name, value: name }))
})
const ataOptions = computed(() =>
  store.getPanels
    .filter((panel) => panel.name === selectedPanelName.value)
    .sort((left, right) => left.ata.localeCompare(right.ata))
    .map((panel) => ({ label: panel.ata, value: panel.ata }))
)
const arrayChanged = computed(
  () => !checkArrayEquals(props.original.signature_panel, props.compdoc.signature_panel)
)
function changed(field: keyof ICompDoc): '' | 'warning' {
  return props.original[field] === props.compdoc[field] ? '' : 'warning'
}

function selectPanel(name: string | null): void {
  props.compdoc.panel_name = name || ''
  props.compdoc.panel = null
  props.compdoc.ata = null
}

function selectAta(ata: string | null): void {
  const selected = store.getPanels.find(
    (panel) => panel.name === selectedPanelName.value && panel.ata === ata
  )
  props.compdoc.panel = selected?.id ?? null
  props.compdoc.ata = selected?.ata ?? null
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
