<template>
    <n-modal v-model:show="popup.visible" preset="card" :title="'Download ' + popup.content" :style="{ width: '700px' }"
        :mask-closable="false" transform-origin="center">
        <n-alert :title="popup.title" :type="popup.status">
            <template #icon>
                <n-spin v-if="popup.status == ''" size="tiny" />
            </template>
            <n-text v-if="popup.status == ''"> Preparing resources momentarily. A download button will become active
                once ready.
            </n-text>
            <n-text v-else-if="popup.status == 'success'"> The file is now prepared and ready for download. </n-text>
            <n-text v-else> An error occured while preparing the file. </n-text>
        </n-alert>
        <n-flex justify="center" style="margin-top: 24px">
            <n-button :disabled="!popup.download" @click="downloadExcel">
                <template #icon>
                    <ArrowDown24Regular />
                </template>
                Download
            </n-button>
        </n-flex>
    </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { NSpace, NCard } from 'naive-ui';
import axios from 'axios'
import { ArrowDown24Regular, FlashSettings20Filled } from '@vicons/fluent';

const popup = ref({
    visible: false,
    download: false,
    title: "",
    status: "",
    content: "",
})

const route = useRoute()

let downloadButton: HTMLAnchorElement
let urlObj: string

async function prepareExcel() {
    try {
        const res = await axios.get(`${axios.defaults.baseURL}/${route.params.project}/compdocs/excel/`, {
            responseType: 'blob'
        })

        urlObj = URL.createObjectURL(res.data)
        downloadButton = document.createElement('a')
        downloadButton.href = urlObj
        downloadButton.download = `${(route.params.project as string).toUpperCase()} Compliance Documents.xlsx`
        document.body.appendChild(downloadButton)

        popup.value.download = true
        popup.value.title = "Ready"
        popup.value.status = "success"
    } catch {
        window.$notification.error({
            duration: 3000,
            title: "Error",
            content: "Something went wrong.",
        })
        popup.value.title = "Error"
        popup.value.status = "error"
    }


}

async function downloadExcel() {
    downloadButton.click()
    downloadButton.remove()
    URL.revokeObjectURL(urlObj)
    popup.value.visible = false
}

function openModal(content: string) {
    popup.value = {
        visible: true,
        title: "Preparing " + content + " File",
        content: content,
        status: "",
        download: false
    }
    setTimeout(() => prepareExcel(), 1000)
}

onMounted(() => {

});

defineExpose({
    openModal
})
</script>