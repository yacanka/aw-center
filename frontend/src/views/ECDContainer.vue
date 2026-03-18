<script setup lang="ts">
import { h, ref, onMounted } from 'vue'
import { NButton, NDataTable, NSpace, NTag, NSpin, NUpload } from 'naive-ui'

import Watcher from '@/views/dcc/Watcher.vue';
import SubtaskGenerator from '@/views/dcc/SubtaskGenerator.vue';
import ExcelSubtaskGenerator from '@/views/dcc/ExcelSubtaskGenerator.vue';
import Unauthorized from '@/views/Unauthorized.vue';
import DCCCreator from '@/views/dcc/DCCCreator.vue';
import { useDccStore } from '@/stores/api';
import { IUser } from '@/models/jira';
import { nullCheck } from '@/utils/general';

const activeTab = ref("");
const access = ref(true)
const sessionId = ref()
const store = useDccStore()
const jiraClientInfo = ref<IUser>()

async function connectJiraAccount() {
    try {
        jiraClientInfo.value = await store.checkSession(sessionId.value)
        localStorage.setItem("jira>session_id", sessionId.value)
        store.setSessionId(sessionId.value)
        const savedTab = localStorage.getItem("jira>active_tab")
        activeTab.value = (savedTab ? savedTab : "");
        sessionField.value.visible = false
    } catch (e) {
        window.$message.error("Session ID is not valid. Enter new one.")
        showSessionPopup()
    }
}

const sessionField = ref({
    visible: false,
    title: "Jira Session ID",
    onClick: connectJiraAccount
})

function onStart() {
    if (access.value) {
        sessionId.value = localStorage.getItem("jira>session_id")
        if (sessionId.value) {
            connectJiraAccount()
        } else {
            window.$message.info("Before start, Session ID is required.")
            showSessionPopup()
        }
    }
}

function disconnectJiraAccount() {
    localStorage.removeItem("jira>session_id")
    store.setSessionId("")
    onStart()
}

onMounted(async () => {
    //view.value = checkPermission("view_jira_dcc")
    onStart()
})


const handleTabChange = (tab: string) => {
    connectJiraAccount() // Just checking if session is still available
    localStorage.setItem('jira>active_tab', tab);
    activeTab.value = tab;
};

function showSessionPopup() {
    sessionField.value.visible = true
}
</script>

<template>
    <div v-if="access">
        <n-flex v-if="sessionField.visible" justify="center">
            <n-card :title="sessionField.title" style="width: 50vw; min-width: 300px">
                <n-input v-model:value="sessionId" @keydown.enter="sessionField.onClick" />
                <n-flex justify="center" style="margin-top: 10px">
                    <n-button type="info" @click="sessionField.onClick" :disabled="nullCheck(sessionId)">Ok</n-button>
                </n-flex>
            </n-card>
        </n-flex>

        <n-space horizontal justify="space-between">
            <n-tabs v-if="!sessionField.visible" placement="top" v-model:value="activeTab"
                @update:value="handleTabChange" style="width: 80vw;">
                <template #suffix>
                    <n-tag type="success" closable @close="disconnectJiraAccount">
                        Connected JIRA as {{ jiraClientInfo?.displayName }}
                    </n-tag>
                </template>
                <n-tab-pane name="watcher" tab="Watcher">
                    <n-divider style="margin: 0 0px 10px 0;" />
                    <Watcher />
                </n-tab-pane>
                <n-tab-pane name="dcc" tab="DCC Creator">
                    <n-divider style="margin: 0 0px 10px 0;" />
                    <DCCCreator />
                </n-tab-pane>
                <n-tab-pane name="subtask" tab="Subtask Generator (List)">
                    <n-divider style="margin: 0 0px 10px 0;" />
                    <SubtaskGenerator />
                </n-tab-pane>
                <n-tab-pane name="excelSubtask" tab="Subtask Generator (Excel)">
                    <n-divider style="margin: 0 0px 10px 0;" />
                    <ExcelSubtaskGenerator />
                </n-tab-pane>
            </n-tabs>
        </n-space>
    </div>
    <div v-else>
        <Unauthorized />
    </div>
</template>

<style scoped>
:deep(.no-mask .n-modal-mask) {
    display: none !important;
}
</style>