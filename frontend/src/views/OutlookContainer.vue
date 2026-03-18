<script setup lang="ts">
import { h, ref } from 'vue'
import { NUpload, NUploadDragger, NButton, NCard, NDataTable, useMessage, NSwitch } from 'naive-ui'
import { useOutlookStore } from '@/stores/api'
import axios from 'axios'
import { useRouter } from 'vue-router'

const router = useRouter()
const store = useOutlookStore()
const fileList = ref<any[]>([])
const msg = ref<null | IMsg>(null)
const useInline = ref(true)
const taskStatus = ref({
    visible: false,
    title: "",
    status: "",
    description: "",
    module: ""
})

const columns = [
    { title: 'Name', key: 'name' },
    {
        title: 'Size', key: 'size',
        render: (row: IAttachment) => `${(row.size / 1024).toFixed(1)} KB`
    },
    { title: 'MIME', key: 'mime' },
    {
        title: 'Actions',
        key: 'action',
        render: (row: IAttachment) => {
            if (row.download_url) {
                return h('a', { href: axios.defaults.baseURL + row.download_url, target: '_blank' }, 'Download')
            }
            if (row.content_base64) {
                const href = `data:${row.mime};base64,${row.content_base64}`
                return h('a', { href, download: row.name }, 'Download (inline)')
            }
            return '—'
        }
    }
]

function classifyWithMsgSubject(str: string) {
    if (!str || typeof str !== 'string') return null;

    const rules = [
        {
            regex: /crb\s+\d+/i,// regex: /^[a-zçğıöşü]+\s+crb+\s+\d+\s+call$/i,
            module: "ecrTask",
            label: "CRB CALL detected",
            message: "Detects ECR attachments in emails. Reads the ECR. Creates JIRA task and its subtaks related to ECR."
        },
    ]

    for (const rule of rules) {
        if (rule.regex.test(str.trim())) {
            return {
                matched: true,
                module: rule.module,
                label: rule.label,
                description: rule.message,
                original: str.trim()
            };
        }
    }

    return null
}

function runMailTask(message: IMsg) {
    console.log(message)
    const classified = classifyWithMsgSubject(message.mail.subject)
    if (classified) {
        taskStatus.value.status = "success"
        taskStatus.value.title = classified.label
        taskStatus.value.description = classified.description
        taskStatus.value.module = classified.module
    } else {
        window.$message.warning("Unknown mail task")
    }
}

async function sendFile() {
    taskStatus.value.status = ""
    if (fileList.value.length === 0) {
        window.$message.warning('Önce .msg dosyası seçin.')
        return
    }
    const file = fileList.value[0].file as File
    const fd = new FormData()
    fd.append('file', file)
    fd.append('inline', useInline.value ? 'true' : 'false')

    try {
        window.$loadingBar.start()
        const res = await store.parseMsg(fd)
        msg.value = res
        runMailTask(res)
    } catch (e: any) {
        console.error(e)
        window.$loadingBar.error()
    } finally {
        window.$loadingBar.finish()
    }
    fileList.value = []
}

function handleItemHeaderClick() {

}
</script>

<template>
    <div>
        <n-alert v-show="taskStatus.status != ''" :title="taskStatus.title" :type="taskStatus.status" closable>
            <n-text> {{ taskStatus.description }} </n-text>
            <n-flex justify="center" style="margin: 8px">
                <n-button v-if="taskStatus.status == 'success'" @click="router.push({ name: taskStatus.module })">
                    Start Task
                </n-button>
            </n-flex>
        </n-alert>
        <n-card title="Upload MSG file and Parse">
            <div>
                <div style="margin: 0px 0px 8px 8px;">
                    <strong style="margin-right: 8px;">Embedded attachments (base64):</strong>
                    <NSwitch v-model:value="useInline" />
                </div>
            </div>
            <NUpload v-model:file-list="fileList" accept=".msg" :max="1" :show-file-list="true"
                :custom-request="sendFile" :default-upload="true">
                <NUploadDragger>
                    Click or drag .msg file to this area to upload
                </NUploadDragger>
            </NUpload>
        </n-card>

        <n-card v-if="msg" title="Mail Info">
            <div>
                <div><b>Subject:</b> {{ msg.mail.subject }}</div>
                <div><b>From:</b> {{ msg.mail.sender }}</div>
                <n-space>
                    <b>To:</b>
                    <n-scrollbar style="width: 75vw; max-height: 100px;">{{ msg.mail.to }}</n-scrollbar>
                </n-space>
                <n-space>
                    <b>CC:</b>
                    <n-scrollbar style="width: 75vw; max-height: 100px;">{{ msg.mail.cc }}</n-scrollbar>
                </n-space>
                <div><b>Date:</b> {{ msg.mail.date }}</div>
            </div>
            <div v-if="msg.mail.body_html">
                <n-collapse @item-header-click="handleItemHeaderClick" arrow-placement="right">
                    <n-collapse-item title="Body" name="body" display-directive="if">
                        <n-card>
                            <div v-html="msg.mail.body_html"></div>
                        </n-card>
                    </n-collapse-item>
                </n-collapse>
            </div>
        </n-card>

        <n-card v-if="msg" title="Attachments">
            <NDataTable :columns="columns" :data="msg.attachments" :bordered="false" />
        </n-card>
    </div>
</template>

<style scoped>
pre {
    background: #f6f6f6;
    padding: 8px;
    border-radius: 6px;
}
</style>
