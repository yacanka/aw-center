<template>
  <n-modal
    :show="showModal"
    preset="card"
    title="Document Information"
    centered
    :style="{ width: 'min(960px, 96vw)', maxHeight: '94vh', overflow: 'auto' }"
    :mask-closable="true"
    @update:show="handleVisibilityChange"
  >
    <template #header-extra>
      <n-button
        v-if="popupMode === 'view' && canEdit"
        ghost
        type="warning"
        size="small"
        aria-label="Edit compliance document"
        @click="setUpdateMode"
      >
        <template #icon><Edit24Regular /></template>
      </n-button>
    </template>
    <n-form ref="formRef" :model="compdoc" :rules="rules">
      <n-flex vertical :size="12">
        <CompDocIdentityFields
          :compdoc="compdoc"
          :original="originalCompdoc"
          :readonly="readonly"
        />
        <CompDocReferenceFields
          :compdoc="compdoc"
          :original="originalCompdoc"
          :readonly="readonly"
          :has-extra-fields="hasExtraFields"
        />
        <CompDocOwnershipFields
          :compdoc="compdoc"
          :original="originalCompdoc"
          :readonly="readonly"
        />
        <CompDocWorkflowFields :compdoc="compdoc" :editable="popupMode === 'new'" />
        <CompDocNotesFields
          :compdoc="compdoc"
          :original="originalCompdoc"
          :readonly="readonly"
          :show-change-reason="popupMode === 'update'"
        />
        <CompDocHistory :history="compdoc.history" @open="loadHistory" />
      </n-flex>
    </n-form>
    <template #action>
      <n-button
        v-if="popupMode === 'new' || (popupMode === 'update' && canEdit)"
        :type="popupMode === 'new' ? 'success' : 'warning'"
        @click="save"
      >
        {{ popupMode === 'new' ? 'Create' : 'Update' }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { Edit24Regular } from '@vicons/fluent'
import CompDocHistory from '@/components/compdoc/CompDocHistory.vue'
import CompDocIdentityFields from '@/components/compdoc/CompDocIdentityFields.vue'
import CompDocNotesFields from '@/components/compdoc/CompDocNotesFields.vue'
import CompDocOwnershipFields from '@/components/compdoc/CompDocOwnershipFields.vue'
import CompDocReferenceFields from '@/components/compdoc/CompDocReferenceFields.vue'
import CompDocWorkflowFields from '@/components/compdoc/CompDocWorkflowFields.vue'
import { useCompDocEditor } from '@/composables/compdoc/editor'
import type { ICompDoc } from '@/models/compdocs'

const props = withDefaults(defineProps<{ canEdit?: boolean }>(), { canEdit: false })
const {
  compdoc,
  formRef,
  handleVisibilityChange,
  hasExtraFields,
  loadHistory,
  openModal,
  originalCompdoc,
  popupMode,
  readonly,
  rules,
  save,
  setUpdateMode,
  showModal
} = useCompDocEditor(toRef(props, 'canEdit'))

defineExpose<{ openModal: (value: ICompDoc, mode: string) => void }>({ openModal })
</script>
