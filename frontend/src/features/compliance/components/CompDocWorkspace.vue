<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowReset24Regular, Delete24Regular } from '@vicons/fluent'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import CompDocActivity from '@/features/compliance/components/CompDocActivity.vue'
import CompDocContextHelp from '@/features/compliance/components/CompDocContextHelp.vue'
import CompDocOverview from '@/features/compliance/components/CompDocOverview.vue'
import CompDocReviewPanel from '@/features/compliance/components/CompDocReviewPanel.vue'
import CompDocTrackingPanel from '@/features/compliance/components/CompDocTrackingPanel.vue'
import CompDocTransitionPanel from '@/features/compliance/components/CompDocTransitionPanel.vue'
import CompDocWorkPanel from '@/features/compliance/components/CompDocWorkPanel.vue'
import { statusColors } from '@/features/compliance/api/compdocCatalog'
import {
  getCompdocReference,
  humanizeCompdocStatus
} from '@/features/compliance/api/compdocWorkspace'
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
  changed: []
}>()

const statusLabel = computed(() => humanizeCompdocStatus(props.document?.status))
const reference = computed(() => (props.document ? getCompdocReference(props.document) : ''))
const statusColor = computed(() => statusColors[String(props.document?.status || '')])
const activeTab = ref('overview')

watch(
  () => props.document?.id,
  () => (activeTab.value = 'overview')
)
watch(
  () => props.show,
  (show) => {
    if (!show) activeTab.value = 'overview'
  }
)
watch(
  () => props.canEdit,
  (canEdit) => {
    if (!canEdit && activeTab.value === 'transition') activeTab.value = 'overview'
  }
)
</script>

<template>
  <n-drawer
    :show="show"
    width="min(720px, 96vw)"
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
          <n-flex align="center" size="small">
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
          </n-flex>
        </n-space>
      </template>

      <n-tabs v-model:value="activeTab" type="line" animated class="workspace-tabs">
        <n-tab-pane name="overview" tab="Overview" display-directive="show:lazy">
          <div class="workspace-pane-heading">
            <n-text strong>Quick actions</n-text>
            <CompDocContextHelp tab="overview" :active="show && activeTab === 'overview'" />
          </div>
          <CompDocOverview
            :document="document"
            :can-edit="canEdit"
            @view="emit('view', document)"
            @edit="emit('edit', document)"
            @export="emit('export')"
            @copy="emit('copy', document)"
          />
        </n-tab-pane>
        <n-tab-pane name="tracking" tab="Tracking & Alerts" display-directive="show:lazy">
          <div class="workspace-pane-heading">
            <n-text strong>Tracking & alerts</n-text>
            <CompDocContextHelp tab="tracking" :active="show && activeTab === 'tracking'" />
          </div>
          <CompDocTrackingPanel
            :show="show && activeTab === 'tracking'"
            :document="document"
            :project="project"
            :can-edit="canEdit"
          />
        </n-tab-pane>
        <n-tab-pane name="ownership" tab="Ownership" display-directive="show:lazy">
          <div class="workspace-pane-heading">
            <n-text strong>Ownership & next action</n-text>
            <CompDocContextHelp tab="ownership" :active="show && activeTab === 'ownership'" />
          </div>
          <CompDocWorkPanel
            :show="show && activeTab === 'ownership'"
            :project="project"
            :document="document"
            :can-edit="canEdit"
            @changed="emit('changed')"
          />
        </n-tab-pane>
        <n-tab-pane name="reviews" tab="Review & Approval" display-directive="show:lazy">
          <div class="workspace-pane-heading">
            <n-text strong>Review & approval</n-text>
            <CompDocContextHelp tab="reviews" :active="show && activeTab === 'reviews'" />
          </div>
          <CompDocReviewPanel
            :show="show && activeTab === 'reviews'"
            :project="project"
            :document="document"
            :can-edit="canEdit"
            @changed="emit('changed')"
          />
        </n-tab-pane>
        <n-tab-pane v-if="canEdit" name="transition" tab="Transition" display-directive="show:lazy">
          <div class="workspace-pane-heading">
            <n-text strong>Record transition</n-text>
            <CompDocContextHelp tab="transition" :active="show && activeTab === 'transition'" />
          </div>
          <CompDocTransitionPanel
            :show="show && activeTab === 'transition'"
            :project="project"
            :document="document"
            @changed="emit('changed')"
          />
        </n-tab-pane>
        <n-tab-pane name="activity" tab="Activity" display-directive="show:lazy">
          <div class="workspace-pane-heading">
            <n-text strong>Activity</n-text>
            <CompDocContextHelp tab="activity" :active="show && activeTab === 'activity'" />
          </div>
          <CompDocActivity
            :show="show && activeTab === 'activity'"
            :project="project"
            :document="document"
          />
        </n-tab-pane>
      </n-tabs>

      <template #footer>
        <n-flex justify="space-between" align="center" class="workspace-footer">
          <n-text depth="3">Select another row to switch context.</n-text>
          <n-button
            v-if="canDelete"
            :type="document.is_archived ? 'success' : 'error'"
            ghost
            @click="emit('delete', document)"
          >
            <template #icon>
              <ArrowReset24Regular v-if="document.is_archived" />
              <Delete24Regular v-else />
            </template>
            {{ document.is_archived ? 'Restore' : 'Archive' }}
          </n-button>
        </n-flex>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>
