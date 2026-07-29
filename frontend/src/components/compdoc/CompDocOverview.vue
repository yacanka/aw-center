<script setup lang="ts">
import {
  ArrowDownload24Regular,
  Clipboard24Regular,
  Edit24Regular,
  Eye24Regular
} from '@vicons/fluent'
import type { ICompDoc } from '@/models/compdocs'
import { joinCompdocValues } from '@/services/compdocWorkspace'

defineProps<{ document: ICompDoc; canEdit: boolean }>()
const emit = defineEmits<{
  view: []
  edit: []
  export: []
  copy: []
}>()
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
    <n-descriptions label-placement="top" :column="2" bordered size="small">
      <n-descriptions-item label="Panel">{{
        document.panel || 'Not assigned'
      }}</n-descriptions-item>
      <n-descriptions-item label="ATA">{{ document.ata || 'Not assigned' }}</n-descriptions-item>
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
      <n-descriptions-item label="Signature panels" :span="2">
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
