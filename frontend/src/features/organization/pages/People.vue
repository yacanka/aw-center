<template>
  <n-tabs v-model:value="activeProject" @update:value="selectProject">
    <n-tab-pane
      v-for="project in store.getEnabledProjects"
      :key="project.slug"
      :name="project.slug"
      :tab="project.name"
    />
  </n-tabs>
  <n-search
    v-model:value="searchText"
    default-mod="name"
    placeholder="Search"
    style="width: min(500px, 100%); margin-bottom: 12px"
    @search="handleDirectorySearch"
  />
  <n-card title="People List" class="app-table-container">
    <n-button
      v-if="canManageDirectory"
      @click="peopleUpload.openModal()"
      :focusable="false"
      style="margin: 0 8px 8px 0"
    >
      <template #icon>
        <n-icon size="24">
          <Add24Regular />
        </n-icon>
      </template>
      Import People
    </n-button>
    <n-button
      v-if="canManageDirectory"
      @click="peoplePopup.openModal({ project: activeProject }, 'new')"
      :focusable="false"
      style="margin: 0 0 8px 0"
    >
      <template #icon>
        <n-icon size="24">
          <Add24Regular />
        </n-icon>
      </template>
      New Person
    </n-button>

    <n-data-table
      :loading="store.isLoading"
      striped
      :columns="columns"
      :data="store.getPeople"
      :pagination="pagination"
      :remote="true"
      @update:page="handlePageUpdate"
      @update:page-size="handlePageSizeUpdate"
      ref="table"
      :row-key="rowKey"
      :scroll-x="940"
      size="tiny"
      max-height="800"
    />
  </n-card>
  <PeoplePopup ref="peoplePopup" />
  <PeopleUpload ref="peopleUpload" />
</template>

<script setup>
import { computed, ref, onMounted, h } from 'vue'
import { NSpace, NButton } from 'naive-ui'

import { Edit24Regular, Delete24Regular, Add24Regular } from '@vicons/fluent'
import { useOrganizationController } from '@/features/organization/composables/organizationController'
import { useSessionStore } from '@/features/session/stores/session'
import PeoplePopup from '@/features/organization/components/PeoplePopup.vue'
import PeopleUpload from '@/features/organization/components/PeopleUpload.vue'
import NSearch from '@/shared/components/NSearch.vue'

const store = useOrganizationController()
const session = useSessionStore()
const canManageDirectory = computed(() =>
  session.hasEffectiveRole('orgs', 'manage_people_directory')
)
const peoplePopup = ref(null)
const peopleUpload = ref(null)

const searchText = ref('')
const directorySearch = ref('')
const currentPage = ref(1)
const currentPageSize = ref(24)
const pagination = computed(() => ({
  page: currentPage.value,
  pageSize: currentPageSize.value,
  itemCount: store.peoplePagination.count,
  showSizePicker: true,
  pageSizes: [24, 50, 100]
}))

const columns = [
  {
    width: 48
  },
  {
    title: 'ID',
    key: 'person_id',
    width: 180
  },
  {
    title: 'Name',
    key: 'name',
    ellipsis: {
      tooltip: true
    },
    width: 320
  },
  {
    title: 'Email',
    key: 'email',
    ellipsis: {
      tooltip: true
    },
    width: 320
  },
  {
    title: 'Action',
    key: 'actions',
    width: 120,
    render(row, index) {
      if (!canManageDirectory.value) return null
      return h(
        NSpace,
        {},
        {
          default: () => [
            h(
              NButton,
              {
                ghost: true,
                size: 'tiny',
                type: 'warning',
                focusable: false,
                renderIcon: () => h(Edit24Regular),
                onClick: () => {
                  peoplePopup.value.openModal(row, 'update')
                }
              },
              { default: () => null }
            ),
            h(
              NButton,
              {
                ghost: true,
                size: 'tiny',
                type: 'error',
                focusable: false,
                renderIcon: () => h(Delete24Regular),
                onClick: () => {
                  window.$dialog.error({
                    title: 'Delete',
                    content: 'Are you sure to delete?',
                    positiveText: 'Yes',
                    negativeText: 'No',
                    onPositiveClick: () => {
                      store.deletePerson(row.id)
                    }
                  })
                }
              },
              { default: () => null }
            )
          ]
        }
      )
    }
  }
]

function rowKey(row) {
  return row.id
}

const ACTIVE_PROJECT_KEY = 'peopleActiveProject'
const activeProject = ref(null)

function fetchPeoplePage() {
  void store
    .fetchPeople(true, {
      page: currentPage.value,
      page_size: currentPageSize.value,
      search: directorySearch.value
    })
    .catch(() => undefined)
}

function handleDirectorySearch(query) {
  const normalizedQuery = query.trim()
  if (normalizedQuery == directorySearch.value) return
  directorySearch.value = normalizedQuery
  currentPage.value = 1
  fetchPeoplePage()
}

function handlePageUpdate(page) {
  currentPage.value = page
  fetchPeoplePage()
}

function handlePageSizeUpdate(pageSize) {
  currentPageSize.value = pageSize
  currentPage.value = 1
  fetchPeoplePage()
}

async function selectProject(projectSlug) {
  activeProject.value = projectSlug
  store.setProject(projectSlug)
  localStorage.setItem(ACTIVE_PROJECT_KEY, projectSlug)
  currentPage.value = 1
  await fetchPeoplePage()
}

onMounted(async () => {
  await store.fetchProjects()
  const savedProject = localStorage.getItem(ACTIVE_PROJECT_KEY)
  const projectSlug = store.getEnabledProjects.some((project) => project.slug === savedProject)
    ? savedProject
    : store.getEnabledProjects[0]?.slug
  if (projectSlug) await selectProject(projectSlug)
})
</script>
