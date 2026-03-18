<template>
    <n-flex justify="center">
        <n-card title="JIRA DCC Creator" style="width: 90%;">
            <n-grid cols=6 x-gap=12 y-gap="18">
                <n-grid-item span=5>
                    <n-input v-model:value="generator.url" type="url" placeholder="Enter Url" @keydown.enter.prevent />
                </n-grid-item>
                <n-grid-item span=1>
                    <n-button type="info" ghost style="width: 100%"
                        :disabled="loadingBar.status == 'default' || generator.url == ''" @click="createDcc">Create</n-button>
                </n-grid-item>
                <n-grid-item span=5>
                    <n-progress v-if="loadingBar.show" type="line" :status="loadingBar.status"
                        :percentage="loadingBar.percentage" indicator-placement="outside" :height="30"
                        :processing="loadingBar.status == 'default' ? true : false">
                    </n-progress>
                </n-grid-item>
                <n-grid-item span=1>
                    <n-ellipsis v-if="loadingBar.status == 'default' ? true : false" style="margin-top: 4px"> {{
                        loadingBar.content }}</n-ellipsis>
                </n-grid-item>
            </n-grid>
        </n-card>
    </n-flex>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { useRoute } from 'vue-router'

const route = useRoute()
const generator = ref({
    JSESSIONID: "",
    url: ""
})

const loadingBar = ref({
    show: false,
    status: "",
    percentage: 0,
    content: ""
})

function createDcc() {
    loadingBar.value.show = true
    loadingBar.value.status = "default"
    loadingBar.value.percentage = 0
    axios.post(`${axios.defaults.baseURL}/dcc/create_queue/`, generator.value
    ).then((res) => {
        console.log(res)
        const eventSource = new EventSource(`${axios.defaults.baseURL}/dcc/create_dcc_stream/${res.data}`);
        eventSource.onmessage = function (event) {
            const data = JSON.parse(event.data);
            console.log(data)
            if (data.status == "progress") {
                loadingBar.value.percentage = data.percentage
                loadingBar.value.content = `${data.content}`
            } else if (data.status == "success") {
                eventSource.close()
                loadingBar.value.percentage = 100
                loadingBar.value.status = "success"
                loadingBar.value.content = ""

                const byteCharacters = atob(data.content)
                const byteArray = new Uint8Array([...byteCharacters].map(c => c.charCodeAt(0)))
                const blob = new Blob([byteArray], { type: 'text/plain' })

                const link = document.createElement("a")
                link.href = URL.createObjectURL(blob)
                link.download = data.filename
                link.click()
                link.remove()
                URL.revokeObjectURL(link.href)

                window.$notification.success({
                    title: 'Success',
                    description: "DCC created successfully.",
                    duration: 3000
                })
            }
            else if (data.status == "warning") {
                eventSource.close()
                loadingBar.value.percentage = 100
                loadingBar.value.status = "warning"
                loadingBar.value.content = ""
                window.$notification.warning({
                    title: 'Warning',
                    description: data.content,
                    duration: 3000
                })
            } else if (data.status == "error") {
                eventSource.close()
                loadingBar.value.percentage = 100
                loadingBar.value.status = "error"
                loadingBar.value.content = ""
                window.$notification.error({
                    title: 'Error',
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
})
</script>