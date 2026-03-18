<template>
  <n-search v-model:value="searchText" placeholder="Search" :list="store.getPeople"
    style="width: 500px; margin-bottom: 12px;" />
  <n-card title="People List" style="max-width: 93%">
    <n-button @click="peopleUpload.openModal()" :focusable="false" style="margin: 0 8px 8px 0">
      <template #icon>
        <n-icon size=24>
          <Add24Regular />
        </n-icon>
      </template>
      Import People
    </n-button>
    <n-button @click="peoplePopup.openModal({ project: activeProject }, 'new')" :focusable="false"
      style="margin: 0 0 8px 0">
      <template #icon>
        <n-icon size=24>
          <Add24Regular />
        </n-icon>
      </template>
      New Person
    </n-button>

    <n-data-table :loading="store.isLoading" striped :columns="columns" :data="store.getPeople" :pagination="pagination"
      ref="table" :row-key="rowKey" size="tiny" max-height="800" />
  </n-card>
  <PeoplePopup ref="peoplePopup" />
  <PeopleUpload ref="peopleUpload" />
</template>

<script setup>
import { ref, onMounted, h } from 'vue';
import { NSpace, NButton, NTag } from 'naive-ui'

import { setUser, getUser, isAuthenticated, logout, setProjectName } from "@/stores/user"
import { Edit24Regular, Delete24Regular, Add24Regular, ArrowReset24Regular, Checkmark24Regular } from '@vicons/fluent';
import { useOrgsStore } from '@/stores/api'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import PeoplePopup from '@/components/orgs/PeoplePopup.vue'
import PeopleUpload from '@/components/orgs/PeopleUpload.vue'
import NSearch from '@/components/NSearch.vue'

const router = useRouter()
const store = useOrgsStore()
const peoplePopup = ref(null)
const peopleUpload = ref(null)

const searchText = ref("")
const pagination = {
  pageSize: 24
}

const columns = [
  {
    width: 8
  },
  {
    title: 'ID',
    key: 'person_id',
    render: (row) => {
      return row.person_id
    },
    filter(value, row) {
      return ~row.person_id.indexOf(value)
    },
    width: 180
  },
  {
    title: 'Name',
    key: 'name',
    filter(value, row) {
      return ~row.name.indexOf(value)
    },
    ellipsis: {
      tooltip: true
    },
    width: 320
  },
  {
    title: 'Email',
    key: 'email',
    filter(value, row) {
      return ~row.email.indexOf(value)
    },
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
      return h(NSpace, {}, {
        default: () => [
          h(NButton,
            {
              ghost: true,
              size: 'tiny',
              type: 'warning',
              focusable: false,
              renderIcon: () => h(Edit24Regular),
              onClick: () => {
                peoplePopup.value.openModal(row, "update")
              },
            },
            { default: () => null }
          ),
          h(NButton,
            {
              ghost: true,
              size: 'tiny',
              type: 'error',
              focusable: false,
              renderIcon: () => h(Delete24Regular),
              onClick: () => {
                window.$dialog.error({
                  title: "Delete",
                  content: "Are you sure to delete?",
                  positiveText: "Yes",
                  negativeText: "No",
                  onPositiveClick: () => {
                    store.deletePerson(row.id)
                  },
                })
              }
            },
            { default: () => null }
          )
        ]
      })
    }
  }
]

function rowKey(row) {
  return row.id
}

const activeProject = ref(null)
const activePanel = ref(null)

onMounted(() => {
  const projectTab = localStorage.getItem("activeProjectTab")
  activeProject.value = (projectTab ? projectTab : null);
})

</script>

<style scoped></style>
