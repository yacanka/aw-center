<script setup lang="ts">
import { computed } from 'vue'
import {
  ArrowDownload24Regular,
  Clipboard24Regular,
  Delete24Regular,
  Edit24Regular,
  Eye24Regular
} from '@vicons/fluent'
import type { ICompDoc } from '@/models/compdocs'
import { statusColors } from '@/services/compdocCatalog'
import {
  getCompdocReference,
  humanizeCompdocStatus,
  joinCompdocValues
} from '@/services/compdocWorkspace'
import './CompDocWorkspace.css'

const props = defineProps<{
  show: boolean
  document: ICompDoc | null
  project: string
  canEdit: boolean
  canDelete: boolean
}>()
const emit = defineEmits<{
  'update:show': [value: boolean]
  view: [document: ICompDoc]
  edit: [document: ICompDoc]
  export: []
  copy: [document: ICompDoc]
  delete: [document: ICompDoc]
}>()

const statusLabel = computed(() => humanizeCompdocStatus(props.document?.status))
const reference = computed(() => (props.document ? getCompdocReference(props.document) : ''))
const statusColor = computed(() => statusColors[String(props.document?.status || '')])
</script>

<template>
  <n-drawer
    :show="show"
    width="min(560px, 94vw)"
    placement="right"
    :trap-focus="true"
    @update:show="emit('update:show', $event)"
  >
    <n-drawer-content v-if="document" closable :native-scrollbar="false">
      <template #header>
        <n-space vertical :size="5" class="workspace-heading">
          <n-text depth="3" class="workspace-eyebrow">
            {{ project.toUpperCase() }} · COMPLIANCE DOCUMENT
          </n-text>
          <n-ellipsis :line-clamp="2" class="workspace-title">{{ document.name }}</n-ellipsis>
          <n-space align="center" size="small">
            <n-tag
              :color="
                statusColor
                  ? { color: statusColor.color25, textColor: statusColor.color }
                  : undefined
              "
              :bordered="false"
              size="small"
            >
              {{ statusLabel }}
            </n-tag>
            <n-text depth="3">{{ reference }}</n-text>
          </n-space>
        </n-space>
      </template>

      <section class="workspace-section">
        <n-text strong>Quick actions</n-text>
        <n-flex class="workspace-actions">
          <n-button type="primary" @click="emit('view', document)">
            <template #icon><Eye24Regular /></template>
            Full details
          </n-button>
          <n-button v-if="canEdit" @click="emit('edit', document)">
            <template #icon><Edit24Regular /></template>
            Edit
          </n-button>
          <n-button @click="emit('export')">
            <template #icon><ArrowDownload24Regular /></template>
            Export register
          </n-button>
          <n-button v-if="document.path" @click="emit('copy', document)">
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
          <n-descriptions-item label="ATA">{{
            document.ata || 'Not assigned'
          }}</n-descriptions-item>
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

      <template #footer>
        <n-flex justify="space-between" align="center" class="workspace-footer">
          <n-text depth="3">Double-click another row to switch context.</n-text>
          <n-button v-if="canDelete" type="error" ghost @click="emit('delete', document)">
            <template #icon><Delete24Regular /></template>
            Delete
          </n-button>
        </n-flex>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>
