<template>
  <n-card title="Panel Management">
    <n-tabs v-model:value="activeProject" @update:value="selectProject">
      <n-tab-pane
        v-for="project in store.getEnabledProjects"
        :key="project.slug"
        :name="project.slug"
        :tab="project.display_name"
      />
    </n-tabs>

    <n-button
      :disabled="!activeProject"
      :focusable="false"
      style="margin-bottom: 12px"
      @click="openNewPanel"
    >
      <template #icon
        ><n-icon size="24"><Add24Regular /></n-icon
      ></template>
      New Panel
    </n-button>

    <n-empty
      v-if="!activeProject && !store.isLoading"
      description="No active project is registered."
    />
    <n-data-table
      v-else
      :loading="store.isLoading"
      :columns="columns"
      :data="store.getPanels"
      :pagination="pagination"
      :row-key="panelRowKey"
      striped
    />
  </n-card>
  <PanelsPopup ref="panelPopup" />
</template>

<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { NButton, NSpace, type DataTableColumns } from 'naive-ui'
import { Add24Regular, Delete24Regular, Edit24Regular } from '@vicons/fluent'
import PanelsPopup from '@/components/orgs/PanelsPopup.vue'
import type { IPanel } from '@/models/orgs'
import { useOrgsStore } from '@/stores/organizations'

type PanelPopup = { openModal: (panel: Partial<IPanel>, mode: 'new' | 'update') => void }

const ACTIVE_PROJECT_KEY = 'panelsActiveTab'
const store = useOrgsStore()
const panelPopup = ref<PanelPopup | null>(null)
const activeProject = ref<string | null>(null)
const pagination = { pageSize: 8 }

const columns: DataTableColumns<IPanel> = [
  { title: 'ATA Chapter', key: 'ata', width: 130 },
  { title: 'Name', key: 'name', minWidth: 180 },
  { title: 'Discipline', key: 'discipline', minWidth: 180 },
  {
    title: 'Actions',
    key: 'actions',
    width: 120,
    render: (panel) =>
      h(NSpace, null, {
        default: () => [
          actionButton('warning', Edit24Regular, () =>
            panelPopup.value?.openModal(panel, 'update')
          ),
          actionButton('error', Delete24Regular, () => confirmDelete(panel))
        ]
      })
  }
]

function actionButton(type: 'warning' | 'error', icon: object, onClick: () => void) {
  return h(NButton, {
    ghost: true,
    size: 'small',
    type,
    focusable: false,
    renderIcon: () => h(icon),
    onClick
  })
}

function confirmDelete(panel: IPanel): void {
  const panelId = panel.id
  if (panelId === undefined) return
  window.$dialog.error({
    title: 'Delete Panel',
    content: `Delete ${panel.ata} – ${panel.name}? Its responsible assignments may also be removed.`,
    positiveText: 'Delete',
    negativeText: 'Cancel',
    onPositiveClick: () => store.deletePanel(panelId)
  })
}

function openNewPanel(): void {
  if (!activeProject.value) return
  panelPopup.value?.openModal({ project: activeProject.value }, 'new')
}

function panelRowKey(panel: IPanel): number | string {
  return panel.id ?? panel.ata
}

async function selectProject(projectSlug: string): Promise<void> {
  activeProject.value = projectSlug
  store.setProject(projectSlug)
  localStorage.setItem(ACTIVE_PROJECT_KEY, projectSlug)
  await store.fetchPanels()
}

onMounted(async () => {
  await store.fetchProjects()
  const projects = store.getEnabledProjects
  const savedSlug = localStorage.getItem(ACTIVE_PROJECT_KEY)
  const initialSlug = projects.some((project) => project.slug === savedSlug)
    ? savedSlug
    : projects[0]?.slug
  if (initialSlug) await selectProject(initialSlug)
})
</script>
