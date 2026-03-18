<template>
    <n-space vertical justify='space-around'>
        <n-space justify='space-around'>
            <n-card v-if="jiraInfo.components" title="Project">{{ jiraInfo.components[0].name }} </n-card>
            <n-card v-if="jiraInfo.customfield_45000" title="ECD No">{{ jiraInfo.customfield_45000 }}</n-card>
            <n-card v-if="jiraInfo.customfield_45002" title="DCC Name">{{ jiraInfo.customfield_45002 }}</n-card>

            <n-card v-if="jiraInfo.ecd_path!=undefined" title="ECD Document" :style="jiraInfo.ecd_path ? 'color: green' : 'color: orange'">{{ jiraInfo.ecd_path ? 'Exist' : 'Not Exist'}}</n-card>
            <n-card v-if="jiraInfo.dcc_unsigned_path!=undefined" title="Unsigned DCC" :style="jiraInfo.dcc_unsigned_path ? 'color: green' : 'color: orange'">{{ jiraInfo.dcc_unsigned_path ? 'Exist' : 'Not Exist'}}</n-card>
            <n-card v-if="jiraInfo.dcc_signed_path!=undefined" title="Signed DCC" :style="jiraInfo.dcc_signed_path ? 'color: green' : 'color: orange'">{{ jiraInfo.dcc_signed_path ? 'Exist' : 'Not Exist'}}</n-card>

            <n-card v-if="jiraInfo.generalStatus != undefined" title="Subtasks Status" :style="jiraInfo.generalStatus ? 'color: green' : 'color: orange'"> {{ jiraInfo.generalStatus ? "Subtasks are fully finalized" : "Outstanding subtasks remain"}}</n-card>
        </n-space>
        <n-space justify='space-around'>
          <n-space v-if="jiraInfo.subtasks" v-for="(item, index) in jiraInfo.subtasks" :key="index">
              <n-card size="small" style="width: 400px" content-style="font-size: 12px;">{{ jiraInfo.subtasks[index].fields.summary }}</n-card>
              <n-card size="small" style="width: 80px; text-align:center" content-style="font-size: 12px;" :style="jiraInfo.subtasks[index].fields.status.name == 'Closed' ? 'color: green' : 'color: orange'">{{ jiraInfo.subtasks[index].fields.status.name }}</n-card>
              <n-button size="large" style="height: 100%" @click="goPage(jiraInfo.subtasks[index].key)">Go Page</n-button>
          </n-space>
        </n-space>
    </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import {NSpace, NCard} from 'naive-ui';
import { IJira } from '@/models/jira';

const props = defineProps(['dcc'])
const jiraInfo = ref<IJira>({} as IJira) 

function goPage(url: string){
  url = "https://taijiraprod.dmntai.intra/browse/" + url
  const newWindow = window.open(url, '_blank'); 
  if (newWindow !== null) {
    newWindow.focus();
  }
}

onMounted(() => {
  jiraInfo.value = props.dcc.fields
  jiraInfo.value.dcc_unsigned_path = props.dcc.dcc_unsigned_path
  jiraInfo.value.dcc_signed_path = props.dcc.dcc_signed_path
  jiraInfo.value.ecd_path = props.dcc.ecd_path
  jiraInfo.value.generalStatus = !jiraInfo.value.subtasks.some(item => item.fields.status.name === "Open"); 
});
</script>