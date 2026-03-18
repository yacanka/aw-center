<script setup lang="ts">
import { h, ref, onMounted } from 'vue'
import { NButton, NDataTable, NSpace, NTag, NSpin, NUpload } from 'naive-ui'

import People from '@/views/orgs/People.vue';
import Responsibles from '@/views/orgs/Responsibles.vue';
import Panels from '@/views/orgs/Panels.vue';
import Projects from '@/views/orgs/Projects.vue';
import Unauthorized from '@/views/Unauthorized.vue';

const activeTab = ref();
const view = ref(true)
onMounted(() => {
  if (view.value) {
    const savedTab = localStorage.getItem("orgActiveTab")
    activeTab.value = (savedTab ? savedTab : 'people');
  }
})


const handleTabChange = (tab: string) => {
  localStorage.setItem('orgActiveTab', tab);
  activeTab.value = tab;
};
</script>

<template>
  <div v-if="view">
    <n-scrollbar style="max-height: 88vh; padding-right: 16px">
      <n-tabs placement="left" v-model:value="activeTab" @update:value="handleTabChange">
        <n-tab-pane name="people" tab="People">
          <People />
        </n-tab-pane>
        <n-tab-pane name="responsibles" tab="Responsibles">
          <Responsibles />
        </n-tab-pane>
        <n-tab-pane name="panels" tab="Panels">
          <Panels />
        </n-tab-pane>
        <n-tab-pane name="project" tab="Projects">
          <Projects />
        </n-tab-pane>
      </n-tabs>
    </n-scrollbar>
  </div>
  <div v-else>
    <Unauthorized />
  </div>
</template>