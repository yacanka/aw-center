<script setup lang="ts">
import {
  ArrowDownload24Regular,
  Clipboard24Regular,
  Edit24Regular,
  Eye24Regular
} from '@vicons/fluent'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { joinCompdocValues } from '@/features/compliance/api/compdocWorkspace'
import { useOrganizationController } from '@/features/organization/composables/organizationController'
import { useMediaQuery } from '@/shared/composables/mediaQuery'

const props = defineProps<{ document: ICompDoc; canEdit: boolean }>()
const orgs = useOrganizationController()
const isNarrow = useMediaQuery('(max-width: 640px)')
const emit = defineEmits<{
  view: []
  edit: []
  export: []
  copy: []
}>()

function panelLabel(): string {
  const panel = orgs.getPanels.find((item) => item.id === props.document.panel)
  return panel?.name || 'Not assigned'
}

function panelAta(): string {
  return orgs.getPanels.find((item) => item.id === props.document.panel)?.ata || 'Not assigned'
}
</script>

<template>
  <section class="workspace-section">
    <n-flex class="workspace-actions">
      <n-button type="primary" @click="emit('view')">
        <template #icon><Eye24Regular /></template>
        Full details
      </n-button>
      <n-button v-if="canEdit" @click="emit('edit')">
        <template #icon><Edit24Regular /></template>
        Edit
      </n-button>
      <n-button @click="emit('export')">
        <template #icon><ArrowDownload24Regular /></template>
        Export register
      </n-button>
      <n-button v-if="document.path" @click="emit('copy')">
        <template #icon><Clipboard24Regular /></template>
        Copy path
      </n-button>
    </n-flex>
  </section>
  <section class="workspace-section">
    <n-text strong>Document identity</n-text>
    <n-descriptions label-placement="top" :column="isNarrow ? 1 : 2" bordered size="small">
      <n-descriptions-item label="Panel">{{ panelLabel() }}</n-descriptions-item>
      <n-descriptions-item label="ATA">{{ panelAta() }}</n-descriptions-item>
      <n-descriptions-item label="Cover page">
        {{ joinCompdocValues([document.cover_page_no, document.cover_page_issue]) }}
      </n-descriptions-item>
      <n-descriptions-item label="Technical document">
        {{ joinCompdocValues([document.tech_doc_no, document.tech_doc_issue]) }}
      </n-descriptions-item>
      <n-descriptions-item label="Delivered issue">
        {{ document.delivered_tech_doc_issue || 'Not delivered' }}
      </n-descriptions-item>
      <n-descriptions-item label="Responsible">
        {{ document.responsible || 'Not assigned' }}
      </n-descriptions-item>
      <n-descriptions-item label="Signature panels" :span="isNarrow ? 1 : 2">
        {{ joinCompdocValues(document.signature_panel) }}
      </n-descriptions-item>
    </n-descriptions>
  </section>
  <section class="workspace-section">
    <n-text strong>Requirements</n-text>
    <n-flex v-if="document.requirements.length" class="workspace-tags">
      <n-tag v-for="requirement in document.requirements" :key="requirement" size="small">
        {{ requirement }}
      </n-tag>
    </n-flex>
    <n-text v-else depth="3">No linked requirements.</n-text>
  </section>
  <section v-if="document.notes" class="workspace-section">
    <n-text strong>Notes</n-text>
    <n-card size="small" embedded>{{ document.notes }}</n-card>
  </section>
</template>
