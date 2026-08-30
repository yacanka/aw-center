<template>
  <n-card title="Project Management">
    <n-alert type="info" :show-icon="false" style="margin-bottom: 16px">
      Projects are read from the backend registry. Additions and configuration changes must be made
      in the backend project definition.
    </n-alert>
    <n-data-table
      :loading="store.isLoading"
      :columns="columns"
      :data="store.getProjects"
      :pagination="pagination"
      :row-key="projectRowKey"
      :scroll-x="840"
      striped
    />
  </n-card>
</template>

<script setup lang="ts">
import { h, onMounted } from 'vue'
import { NTag, type DataTableColumns } from 'naive-ui'
import type { IProject } from '@/features/organization/models/orgs'
import { useOrganizationController } from '@/features/organization/composables/organizationController'

const store = useOrganizationController()
const pagination = { pageSize: 8 }

const columns: DataTableColumns<IProject> = [
  {
    title: 'Project',
    key: 'name',
    minWidth: 140,
    sorter: (left, right) => left.name.localeCompare(right.name, 'tr')
  },
  { title: 'Slug', key: 'slug', minWidth: 100 },
  {
    title: 'Capabilities',
    key: 'capabilities',
    minWidth: 190,
    render: (project) => renderTags(project.capabilities, 'info')
  },
  {
    title: 'Effective Roles',
    key: 'roles',
    minWidth: 220,
    render: (project) =>
      renderTags(
        Object.entries(project.roles).flatMap(([domain, role]) =>
          role ? [`${domain}: ${role}`] : []
        ),
        'default'
      )
  }
]

function renderTags(values: string[], type: 'info' | 'default') {
  return values.map((value) =>
    h(NTag, { type, size: 'small', bordered: false, style: 'margin: 2px 4px 2px 0' }, () => value)
  )
}

function projectRowKey(project: IProject): string {
  return project.slug
}

onMounted(() => store.fetchProjects())
</script>
