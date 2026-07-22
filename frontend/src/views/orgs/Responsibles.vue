<template>
  <n-card title="Responsible Management">
    <n-tabs v-model:value="activeProject" @update:value="selectProject">
      <n-tab-pane
        v-for="project in store.getEnabledProjects"
        :key="project.slug"
        :name="project.slug"
        :tab="project.display_name"
      />
    </n-tabs>

    <n-space align="center" style="margin-bottom: 12px">
      <n-button :disabled="!activeProject" :focusable="false" @click="openNewResponsible">
        <template #icon
          ><n-icon size="24"><Add24Regular /></n-icon
        ></template>
        New Responsible
      </n-button>
      <n-select
        v-model:value="activePanel"
        :disabled="!activeProject"
        :options="panelOptions"
        clearable
        placeholder="All panels"
        style="width: 260px"
        @update:value="selectPanel"
      />
    </n-space>

    <n-empty
      v-if="!activeProject && !store.isLoading"
      description="No active project is registered."
    />
    <n-data-table
      v-else
      :loading="store.isLoading"
      :columns="columns"
      :data="store.getResponsibles"
      :pagination="pagination"
      :row-key="responsibleRowKey"
      striped
    />
  </n-card>
  <ResponsiblePopup ref="responsiblePopup" />
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NSpace, type DataTableColumns } from 'naive-ui'
import { Add24Regular, Delete24Regular, Edit24Regular } from '@vicons/fluent'
import ResponsiblePopup from '@/components/orgs/ResponsiblePopup.vue'
import type { IResponsible } from '@/models/orgs'
import { useOrgsStore } from '@/stores/organizations'

type ResponsiblePopupApi = {
  openModal: (responsible: IResponsible, mode: 'new' | 'update') => void
}

const ACTIVE_PROJECT_KEY = 'responsiblesActiveProject'
const ACTIVE_PANEL_KEY = 'responsiblesActivePanel'
const store = useOrgsStore()
const responsiblePopup = ref<ResponsiblePopupApi | null>(null)
const activeProject = ref<string | null>(null)
const activePanel = ref<string | null>(null)
const pagination = { pageSize: 8 }
const panelOptions = computed(() =>
  store.getPanels.map((panel) => ({
    label: `${panel.ata} – ${panel.name}`,
    value: panel.ata
  }))
)

const columns: DataTableColumns<IResponsible> = [
  { title: 'ATA', key: 'panel', width: 90 },
  { title: 'Panel', key: 'panel_name', minWidth: 150 },
  { title: 'Title', key: 'title', width: 100 },
  { title: 'ID', key: 'person_id', width: 100 },
  { title: 'Name', key: 'name', minWidth: 170 },
  { title: 'Email', key: 'email', minWidth: 220 },
  {
    title: 'Actions',
    key: 'actions',
    width: 120,
    render: (responsible) =>
      h(NSpace, null, {
        default: () => [
          actionButton('warning', Edit24Regular, () =>
            responsiblePopup.value?.openModal(responsible, 'update')
          ),
          actionButton('error', Delete24Regular, () => confirmDelete(responsible))
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

function openNewResponsible(): void {
  if (!activeProject.value) return
  responsiblePopup.value?.openModal(
    {
      project: activeProject.value,
      panel: activePanel.value ?? '',
      person_id: '',
      name: '',
      email: '',
      title: ''
    },
    'new'
  )
}

function confirmDelete(responsible: IResponsible): void {
  const responsibleId = responsible.id
  if (responsibleId === undefined) return
  window.$dialog.error({
    title: 'Delete Responsible',
    content: `Remove ${responsible.name} from this project? The people directory is unchanged.`,
    positiveText: 'Delete',
    negativeText: 'Cancel',
    onPositiveClick: () => store.deleteResponsible(responsibleId)
  })
}

function responsibleRowKey(responsible: IResponsible): number | string {
  return responsible.id ?? `${responsible.panel}-${responsible.person_id}`
}

async function selectProject(projectSlug: string): Promise<void> {
  activeProject.value = projectSlug
  activePanel.value = null
  store.setProject(projectSlug)
  localStorage.setItem(ACTIVE_PROJECT_KEY, projectSlug)
  localStorage.removeItem(ACTIVE_PANEL_KEY)
  await store.fetchPanels()
  await store.fetchResponsibles('')
}

async function selectPanel(panelAta: string | null): Promise<void> {
  activePanel.value = panelAta
  if (panelAta) localStorage.setItem(ACTIVE_PANEL_KEY, panelAta)
  else localStorage.removeItem(ACTIVE_PANEL_KEY)
  await store.fetchResponsibles(panelAta ?? '')
}

onMounted(async () => {
  await store.fetchProjects()
  const projects = store.getEnabledProjects
  const savedProject = localStorage.getItem(ACTIVE_PROJECT_KEY)
  const savedPanel = localStorage.getItem(ACTIVE_PANEL_KEY)
  const projectSlug = projects.some((project) => project.slug === savedProject)
    ? savedProject
    : projects[0]?.slug
  if (!projectSlug) return
  await selectProject(projectSlug)
  if (store.getPanels.some((panel) => panel.ata === savedPanel)) await selectPanel(savedPanel)
})
</script>
