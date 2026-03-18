<template>
    <n-flex justify="center">
        <n-card title="JIRA Subtask Generator" style="width: 90%; min-width: 300px;">
            <n-grid cols=6 x-gap=12 y-gap="18">
                <n-grid-item span=5>
                    <n-input v-model:value="generator.url" type="url" placeholder="Enter Url" @keydown.enter.prevent />
                </n-grid-item>
                <n-grid-item span=1>
                    <n-button type="info" ghost style="width: 100%"
                        :disabled="loadingBar.status == 'default' || generator.url == '' || generator.JSESSIONID == ''"
                        @click="createSubtasks">Generate</n-button>
                </n-grid-item>

                <n-grid-item span=6>
                    <n-ellipsis v-if="loadingBar.status == 'default' ? true : false" style=" margin: 0px 0px -12px 0px"> {{
                        loadingBar.content
                    }}</n-ellipsis>
                </n-grid-item>
                <n-grid-item span=6>
                    <n-progress v-if="loadingBar.show" type="line" :status="loadingBar.status"
                        :percentage="loadingBar.percentage" indicator-placement="outside" :height="30"
                        :processing="loadingBar.status == 'default' ? true : false">
                    </n-progress>
                </n-grid-item>
                
                <n-grid-item span=6>
                    <subtask-list v-model:list="generator.list" />
                </n-grid-item>
            </n-grid>
        </n-card>
    </n-flex>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { useRoute } from 'vue-router'
import { useOrgsStore } from '@/stores/api'
import SubtaskList from '@/components/jira/SubtaskList.vue'
import { toTitleCase } from '@/utils/text'
import { NotificationType } from 'naive-ui'

const orgstore = useOrgsStore()
const route = useRoute()
const generator = ref({
    JSESSIONID: "",
    url: "",
    list: [],
})

const loadingBar = ref({
    show: false,
    status: "",
    percentage: 0,
    content: ""
})
type StreamData = {
    status: string
    type: string
    percentage: number
    content: any
}

function createSubtasks() {
    loadingBar.value.show = true
    loadingBar.value.status = "default"
    loadingBar.value.percentage = 0
    axios.post(`${axios.defaults.baseURL}/dcc/create_queue/`, generator.value
    ).then((res) => {
        const eventSource = new EventSource(`${axios.defaults.baseURL}/dcc/create_subtask_stream/${res.data}`);
        eventSource.onmessage = function (event) {
            const data: StreamData = JSON.parse(event.data);
            console.log(data)
            if (data.status == "progress") {
                loadingBar.value.percentage = data.percentage
                loadingBar.value.content = `Creating ${data.content}...`
            } else if (["success", "warning", "error"].includes(data.status)) {
                eventSource.close()
                loadingBar.value.percentage = 100
                loadingBar.value.status = data.status
                loadingBar.value.content = ""
                window.$notification[data.status as NotificationType]({
                    title: toTitleCase(data.status),
                    description: data.content,
                    duration: 3000
                })
            }
        };
        eventSource.onerror = function (err) {
            console.log(err)
            loadingBar.value.status = "error"
            eventSource.close();
        };

    }).catch((err) => {
        console.error(err)
        window.$notification.error({
            title: 'Error',
            description: `Error while uploading file: ${err.response.data.message}`,
        })
    }).finally(() => {
        console.log("END")
    })
}

onMounted(() => {
    const storedSessionID = localStorage.getItem("jira>session_id")
    generator.value.JSESSIONID = storedSessionID ? storedSessionID : ""

    if (orgstore.getPeople.length == 0) {
        orgstore.fetchPeople()
    }
})
</script>