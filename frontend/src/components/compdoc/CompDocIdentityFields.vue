<template>
  <n-card title="Identity" size="small">
    <n-grid responsive="self" item-responsive :x-gap="12" :y-gap="4" :cols="48">
      <n-form-item-gi span="0:48 700:12" path="panel" label="Panel">
        <n-select
          v-model:value="compdoc.panel"
          placeholder="Select Panel"
          :options="orgs.getPanelOptions"
          :disabled="readonly"
          :status="changed('panel')"
          @update:value="syncAtaFromPanel"
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:8" path="ata" label="ATA">
        <n-select
          v-model:value="compdoc.ata"
          placeholder="XX-XX"
          :options="ataOptions"
          :disabled="readonly || !compdoc.panel"
          :status="changed('ata')"
          @update:value="syncPanelFromAta"
        />
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
          :options="orgs.getPanelOptions"
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
          :readonly="readonly"
          :status="changed('cover_page_no')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:8" path="cover_page_issue" label="Issue">
        <n-input
          v-model:value="compdoc.cover_page_issue"
          maxlength="32"
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
import type { ICompDoc } from '@/models/compdocs'
import { useOrgsStore } from '@/stores/organizations'
import { checkArrayEquals } from '@/utils/array'

const props = defineProps<{
  compdoc: ICompDoc
  original: ICompDoc
  readonly: boolean
}>()
const orgs = useOrgsStore()
const arrayChanged = computed(
  () => !checkArrayEquals(props.original.signature_panel, props.compdoc.signature_panel)
)
const ataOptions = computed(() => optionsForPanel(props.compdoc.panel))

function changed(field: keyof ICompDoc): '' | 'warning' {
  return props.original[field] === props.compdoc[field] ? '' : 'warning'
}

function syncAtaFromPanel(panelName: string | null): void {
  const options = optionsForPanel(panelName)
  if (options.some((option) => option.value === props.compdoc.ata)) return
  props.compdoc.ata = options.length === 1 ? options[0].value : ''
}

function syncPanelFromAta(ata: string | null): void {
  const panel = orgs.getPanels.find((item) => item.ata === ata)
  if (panel) props.compdoc.panel = panel.name
}

function optionsForPanel(panelName: string | null) {
  if (!panelName) return []
  return orgs.getPanels
    .filter((panel) => panel.name === panelName)
    .sort((left, right) => left.ata.localeCompare(right.ata))
    .map((panel) => ({ label: panel.ata, value: panel.ata }))
}
</script>
