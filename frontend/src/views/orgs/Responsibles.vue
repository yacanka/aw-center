<template>
   <n-card title="Responsible Management" style="max-width: 93%">
    <n-button @click="responsiblePopup.openModal({project: activeProject}, 'new')" :focusable="false" style="margin: 0 0 6px 0">
      <template #icon>
        <n-icon size=24>
          <Add24Regular/>
        </n-icon>
      </template>
      New Responsible
    </n-button>

    <n-tabs placement="top" v-model:value="activeProject" @update:value="handleProjectChange">
      <n-tab-pane v-for="(project, index) in store.getProjects" :key="index" :name="project.slug" :tab="project.name" />
    </n-tabs>
    <n-tabs v-if="activeProject" placement="top" animated v-model:value="activePanel" @update:value="handlePanelChange" >
      <n-tab-pane v-for="(panel, index) in store.getPanels" :key="index" :name="panel.ata" :tab="panel.ata" />
    </n-tabs>
    
    <n-data-table :loading="store.isLoading" striped :columns="columns" :data="store.getResponsibles" :pagination="pagination" ref="table" :row-key="rowKey" />
  </n-card>
  <ResponsiblePopup ref="responsiblePopup" />
</template>

<script setup>
import { ref, onMounted, h } from 'vue';
import { NSpace, NButton } from 'naive-ui'

import { setUser, getUser, isAuthenticated, logout, setProjectName} from "@/stores/user"
import {Edit24Regular, Delete24Regular, Add24Regular, ArrowReset24Regular, Checkmark24Regular} from '@vicons/fluent';
import { useOrgsStore } from '@/stores/api'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import ResponsiblePopup from '@/components/orgs/ResponsiblePopup.vue'

const router = useRouter()
const store = useOrgsStore()
const responsiblePopup = ref(null)

const pagination = {
  pageSize: 8
}

const columns = [
    {
    title: 'ATA Chapter',
    key: 'panel',
    filter(value, row){
      return ~row.panel.indexOf(value)
    },
    ellipsis: {
      tooltip: true
    },
    width: 120
  },
  {
    title: 'Panel',
    key: 'panel_name',
    filter(value, row){
      return ~row.panel.indexOf(value)
    },
    ellipsis: {
      tooltip: true
    },
  },
  {
    title: 'Title',
    key: 'title',
    filter(value, row){
      return ~row.title.indexOf(value)
    },
    ellipsis: {
      tooltip: true
    },
  },
  {
    title: 'ID',
    key: 'person_id',
    filter(value, row){
      return ~row.person_id.indexOf(value)
    },
    ellipsis: {
      tooltip: true
    },
  },
  {
    title: 'Name',
    key: 'name',
    filter(value, row){
      return ~row.name.indexOf(value)
    },
    ellipsis: {
      tooltip: true
    },
  },
  {
    title: 'Email',
    key: 'email',
    filter(value, row){
      return ~row.email.indexOf(value)
    },
    ellipsis: {
      tooltip: true
    },
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
                responsiblePopup.value.openModal(row, "update")
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

const activeProject = ref(null)
const activePanel = ref(null)

const handleProjectChange = (tab) => {
  store.setProject(tab)
  store.fetchPanels()
  store.fetchResponsibles("")
  localStorage.setItem('activeProjectTab', tab);
  activePanel.value = null;
  activeProject.value = tab;
};

const handlePanelChange = (tab) => {
  store.fetchResponsibles(activeProject.value, tab)
  localStorage.setItem('activePanelTab', tab);
  activePanel.value = tab;
};



onMounted(()=>{
  store.fetchProjects()
  const projectTab = localStorage.getItem("activeProjectTab")
  activeProject.value = (projectTab ? projectTab : null);
  if(activeProject.value){
    store.setProject(activeProject.value)
    store.fetchPanels()
    store.fetchResponsibles("")
  }
})

</script>

<style scoped>

</style>
