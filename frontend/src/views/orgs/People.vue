<template>
  <n-search
    v-model:value="searchText"
    default-mod="name"
    placeholder="Search"
    style="width: 500px; margin-bottom: 12px"
    @search="handleDirectorySearch"
  />
  <n-card title="People List" style="max-width: 93%">
    <n-button @click="peopleUpload.openModal()" :focusable="false" style="margin: 0 8px 8px 0">
      <template #icon>
        <n-icon size="24">
          <Add24Regular />
        </n-icon>
      </template>
      Import People
    </n-button>
    <n-button
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
import { useOrgsStore } from '@/stores/organizations'
import PeoplePopup from '@/components/orgs/PeoplePopup.vue'
import PeopleUpload from '@/components/orgs/PeopleUpload.vue'
import NSearch from '@/components/NSearch.vue'

const store = useOrgsStore()
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
    width: 8
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
    width: '50',
    render(row, index) {
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

onMounted(() => {
  const projectTab = localStorage.getItem('activeProjectTab')
  activeProject.value = projectTab ? projectTab : null
  fetchPeoplePage()
})
</script>
