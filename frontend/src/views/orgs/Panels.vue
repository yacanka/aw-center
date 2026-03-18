<template>
  <n-card title="Panel Management">
    <n-button @click="panelsPopup.openModal({project: activeTab},'new')" :focusable="false" style="margin: 0px 0 6px 0">
      <template #icon>
        <n-icon size=24>
          <Add24Regular/>
        </n-icon>
      </template>
      New Panel
    </n-button>

    <n-tabs style="card" placement="top" v-model:value="activeTab" @update:value="handleTabChange">
      <n-tab-pane v-for="(project, index) in store.getProjects" :key="index" :name="project.slug" :tab="project.name" />
    </n-tabs>

    <n-data-table :loading="store.isLoading" striped :columns="columns" :data="store.getPanels" :pagination="pagination" ref="table" :row-key="rowKey" />
  </n-card>
  <PanelsPopup ref="panelsPopup" />
</template>

<script setup>
import { ref, onMounted, h } from 'vue';
import { NSpace, NButton } from 'naive-ui'

import { setUser, getUser, isAuthenticated, logout, setProjectName} from "@/stores/user"
import {Edit24Regular, Delete24Regular, Add24Regular, ArrowReset24Regular, Checkmark24Regular} from '@vicons/fluent';
import { useOrgsStore } from '@/stores/api'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import PanelsPopup from '@/components/orgs/PanelsPopup.vue'

const router = useRouter()
const store = useOrgsStore()
const panelsPopup = ref(null)

const pagination = {
  pageSize: 8
}

const columns = [
  {
    title: 'ATA Chapter',
    key: 'ata',
    filter(value, row){
      return ~row.ata.indexOf(value)
    },
    ellipsis: {
      tooltip: true
    },
    width: 120
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
    title: 'Discipline',
    key: 'discipline',
    filter(value, row){
      return ~row.discipline.indexOf(value)
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
                panelsPopup.value.openModal(row, "update")
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
                  store.deletePanel(row.id)
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

const activeTab = ref(null)

const handleTabChange = (tab) => {
  console.log(tab)
  store.setProject(tab)
  store.fetchPanels()
  localStorage.setItem('panelsActiveTab', tab);
  activeTab.value = tab;
};

function rowKey(row){
  return row.id
}

onMounted(()=>{
  store.fetchProjects()
  const savedTab = localStorage.getItem("panelsActiveTab")
  activeTab.value = (savedTab ? savedTab : null);
  if(activeTab.value){
    store.fetchPanels(activeTab.value)
  }
})

</script>

<style scoped>

</style>
