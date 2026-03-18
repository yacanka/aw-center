<template>
    <n-card title="Project Management">
      <n-button @click="projectsPopup.openModal({},'new')" :focusable="false" style="margin-bottom: 12px">
        <template #icon>
          <n-icon size=24>
            <Add24Regular/>
          </n-icon>
        </template>
        New Project
      </n-button>
      <n-data-table :loading="store.isLoading" striped :columns="columns" :data="store.getProjects" :pagination="pagination" ref="table" :row-key="rowKey" />
    </n-card>
  <ProjectsPopup ref="projectsPopup" />
</template>
<script setup>
import { ref, onMounted, h } from 'vue';
import {NSpace, NButton, NInput, NText} from 'naive-ui'
import {Edit24Regular, Delete24Regular, Add24Regular, ArrowReset24Regular, Checkmark24Regular} from '@vicons/fluent';
import { setUser, getUser, isAuthenticated, logout, setProjectName} from "@/stores/user"
import { useOrgsStore } from '@/stores/api'
import ProjectsPopup from '@/components/orgs/ProjectsPopup.vue'

import { RouterLink, RouterView, useRouter } from 'vue-router'

const router = useRouter()
const store = useOrgsStore()
const projectsPopup = ref(null)

const pagination = {
  pageSize: 8
}

const columns = [
  {
    title: 'Name',
    key: 'name',
    filter(value, row){
      return ~row.name.indexOf(value)
    },
    ellipsis: {
      tooltip: true
    },
    width: '40%',
  },
  {
    title: 'Action',
    key: 'actions',
    width: '20%',
    render(row, index) {
      return h(NSpace, {}, {default: () => [
          h(NButton,
            {
              ghost: true,
              size: 'small',
              type: 'warning',
              focusable: false,
              renderIcon: () => h(Edit24Regular),
              onClick: () => {
                projectsPopup.value.openModal(row, "update")
              },
            },
            { default: () => null }
          ),
          h(NButton,
          {
            ghost: true,
            size: 'small',
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
                  store.deleteProject(row.id)
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

function rowKey(row){
  return row.id
}

onMounted(()=>{
  store.fetchProjects()
})

</script>

<style scoped>

</style>
