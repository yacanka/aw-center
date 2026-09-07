<template>
  <n-modal
    :show="showModal"
    preset="card"
    title="Document Information"
    centered
    class="app-modal app-modal--large"
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
          :readonly="formReadonly"
          :show-number-source="popupMode === 'new' || !compdoc.cover_page_no"
          :numbering-available="numberingAvailable"
          :number-source="numberSource"
          @update:number-source="numberSource = $event"
        />
        <n-alert
          v-if="allocationMessage"
          :type="allocationFailed ? 'error' : 'info'"
          :bordered="true"
          title="Numarator"
        >
          {{ allocationMessage }}
          <template v-if="allocationFailed" #action>
            <n-button size="small" :loading="allocationActive" @click="retryAllocation">
              Retry
            </n-button>
          </template>
        </n-alert>
        <CompDocReferenceFields
          :compdoc="compdoc"
          :original="originalCompdoc"
          :readonly="formReadonly"
          :has-extra-fields="hasExtraFields"
        />
        <CompDocOwnershipFields
          :compdoc="compdoc"
          :original="originalCompdoc"
          :readonly="formReadonly"
        />
        <CompDocWorkflowFields :compdoc="compdoc" />
        <CompDocNotesFields
          :compdoc="compdoc"
          :original="originalCompdoc"
          :readonly="formReadonly"
          :show-change-reason="popupMode === 'update'"
        />
        <CompDocHistory :history="compdoc.history" @open="loadHistory" />
      </n-flex>
    </n-form>
    <template #action>
      <n-button
        v-if="popupMode === 'new' || (popupMode === 'update' && canEdit)"
        :type="popupMode === 'new' ? 'success' : 'warning'"
        :loading="allocationActive"
        :disabled="allocationActive || allocationFailed"
        @click="save"
      >
        {{
          numberSource === 'numarator'
            ? 'Get number from Numarator'
            : popupMode === 'new'
              ? 'Create'
              : 'Update'
        }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { Edit24Regular } from '@vicons/fluent'
import CompDocHistory from '@/features/compliance/components/CompDocHistory.vue'
import CompDocIdentityFields from '@/features/compliance/components/CompDocIdentityFields.vue'
import CompDocNotesFields from '@/features/compliance/components/CompDocNotesFields.vue'
import CompDocOwnershipFields from '@/features/compliance/components/CompDocOwnershipFields.vue'
import CompDocReferenceFields from '@/features/compliance/components/CompDocReferenceFields.vue'
import CompDocWorkflowFields from '@/features/compliance/components/CompDocWorkflowFields.vue'
import { useCompDocEditor } from '@/features/compliance/composables/editor'
import type { ICompDoc } from '@/features/compliance/models/compdocs'

const props = withDefaults(defineProps<{ canEdit?: boolean }>(), { canEdit: false })
const {
  compdoc,
  formRef,
  formReadonly,
  handleVisibilityChange,
  hasExtraFields,
  allocationActive,
  allocationFailed,
  allocationMessage,
  loadHistory,
  openModal,
  originalCompdoc,
  popupMode,
  numberingAvailable,
  numberSource,
  rules,
  save,
  retryAllocation,
  setUpdateMode,
  showModal
} = useCompDocEditor(toRef(props, 'canEdit'))

defineExpose<{ openModal: (value: ICompDoc, mode: string) => void }>({ openModal })
</script>
