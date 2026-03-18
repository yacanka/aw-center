<template>
    <n-grid cols="2" x-gap="16">
        <n-gi v-for="ecr in ecrList" hoverable
            @click="() => { if (ecr.approved == undefined) approvePopup.openModal(ecr) }"
            style="margin: 12px 16px 24px 16px;" :class="ecr.approved != undefined ? '' : 'blink'">
            <n-alert :type="ecr.approved != undefined ? (ecr.approved == true ? 'success' : 'error') : 'info'"
                :title="ecr.ecd_no" style="height: 100%;">
                {{ ecr.ecd_title }}
            </n-alert>
        </n-gi>
    </n-grid>

    <n-space vertical :size="12">
        <n-alert v-for="(task, i) in taskQueue" :title="(i + 1) + '. ' + task.title" :type="task.status">
            <template #icon>
                <n-spin v-if="task.status == null" :size="22" />
            </template>

            <n-flex justify="space-between">
                <n-text style="white-space: pre-line"> {{ task.description }} </n-text>
                <n-button v-if="task.status == 'error'" :selectable="false" size="small" style="margin-top: -5px;"
                    @click="currentTask.events.ProgressEvent">Retry</n-button>
            </n-flex>
        </n-alert>

        <n-ellipsis v-if="loadingBar.status == 'default' ? true : false" style=" margin: 0px 0px -12px 0px"> {{
            loadingBar.content
        }}</n-ellipsis>
        <n-progress v-if="loadingBar.show" type="line" :status="loadingBar.status" :percentage="loadingBar.percentage"
            indicator-placement="outside" :height="30" :processing="loadingBar.status == 'default' ? true : false">
        </n-progress>

    </n-space>

    <n-modal v-model:show="sessionPopup.visible" preset="card" :title="sessionPopup.title" :style="{ width: '700px' }"
        :mask-closable="sessionPopup.closable" :closable="sessionPopup.closable" :close-on-esc="sessionPopup.closable"
        transform-origin="center">
        <n-input v-model:value="sessionPopup.input" />
        <n-flex justify="center" style="margin-top: 10px">
            <n-button type="info" @click="sessionPopup.onClick">Ok</n-button>
        </n-flex>
    </n-modal>

    <ApprovePopup ref="approvePopup" :onApprove="(ecr: IEcd) => onEcrApprove(ecr as IEcdCheckItem)"
        :onReject="(ecr: IEcd) => onEcrReject(ecr as IEcdCheckItem)" />
    <EcrUploadPopup ref="ecrUploadPopup" @onSuccess="(file: File, parsed: string | null) => {
        pdfFileList.push(file)
        currentTask.events.ProgressEvent()
    }" />

    <n-modal v-model:show="subtaskListPopup.visible" preset="card" :title="subtaskListPopup.title"
        :style="{ width: '700px' }" :mask-closable="subtaskListPopup.closable" :closable="subtaskListPopup.closable"
        transform-origin="center">
        <subtask-list v-model:list="subtaskListPopup.input" />
        <n-flex justify="center" style="margin-top: 10px">
            <n-button type="info" @click="subtaskListPopup.onClick">Ok</n-button>
        </n-flex>
    </n-modal>
</template>

<script setup lang="ts">
import { create, NAlert, NotificationType, NSpin } from 'naive-ui';
import { h, onMounted, ref } from 'vue';
import { base64ToBytes, nullCheck, sleep } from '@/utils/general';
import { useOutlookStore, useDccStore } from '@/stores/api';
import axios from 'axios';
import { IEcd } from '@/models/ecd';
import ApprovePopup from '@/components/dcc/ApprovePopup.vue';
import { useRouter } from 'vue-router'
import { ISubtaskItem, IUser } from '@/models/jira';
import EcrUploadPopup from './EcrUploadPopup.vue';
import SubtaskList from '../jira/SubtaskList.vue';
import { toTitleCase } from '@/utils/text';

interface IEcdCheckItem extends IEcd {
    approved?: boolean
}

const router = useRouter()
const msg = ref<IMsg>({} as IMsg)
const taskQueue = ref<TaskItem[]>([])
const outlook = useOutlookStore()
const dcc = useDccStore()
const ecrList = ref([] as IEcdCheckItem[])
const currentTask = ref<TaskItem>({} as TaskItem)
const approvePopup = ref()
const userInfo = ref<IUser>()
const ecrUploadPopup = ref()
const sessionPopup = ref<IPopup>({
    closable: false,
    visible: false,
    title: "",
    input: "",
    onClick: null
})
const subtaskListPopup = ref<IPopup>({
    closable: false,
    visible: false,
    title: "",
    input: [] as ISubtaskItem[],
    onClick: null
})

const loadingBar = ref({
    show: false,
    status: "",
    percentage: 0,
    content: ""
})

let pdfFileList: File[] = []
let createdIssueList: string[] = []

const updateEcrApprovementList = () => {
    const leftNumber = ecrList.value.filter(ecr => ecr.approved == undefined).length

    const item = currentTask.value
    item.description = "ECR approval is required: " + leftNumber + " left"

    if (leftNumber == 0) {
        const isAvailable = ecrList.value.some(ecr => ecr.approved == true)
        if (isAvailable) {
            currentTask.value.events.SuccessEvent()
        } else {
            item.status = "error"
            item.description = "No approved ECR found to process."
        }
    }
}

const onEcrApprove = (ecr: IEcdCheckItem) => {
    if (ecr.approved != undefined) return
    ecr.approved = true
    updateEcrApprovementList()
}

const onEcrReject = (ecr: IEcdCheckItem) => {
    if (ecr.approved != undefined) return
    ecr.approved = false
    updateEcrApprovementList()
}

const onSuccess = () => {
    const item = currentTask.value
    item.status = "success"
    item.description = item.descriptions.onSuccess

    nextTask()
}

const onError = (e: string | null = null) => {
    const item = currentTask.value
    item.status = "error"
    item.description = item.descriptions.onError
    if (e) {
        item.description += ("\n > " + e)
    }
}

function nextTask() {
    if (taskList.length != taskQueue.value.length) {
        taskQueue.value.push(taskList[taskQueue.value.length])
        currentTask.value = taskQueue.value[taskQueue.value.length - 1]
        currentTask.value.status = undefined
        currentTask.value.events.ProgressEvent()
    } else {
        window.$message.success("All tasks finished")
        setTimeout(() => {
            router.go(-1)
        }, 20000);
    }
}

function detectEcrSuccess(status: string) {
    const item = currentTask.value
    item.status = "success"
    item.description = `ECR files detected and parsed: ${status}`

    nextTask()
}

async function detectEcrProgress() {
    const item = currentTask.value
    item.status = undefined
    item.description = "Parsing ECR files in attachments..."

    if (pdfFileList.length == 0) {
        const pdfBase64List = msg.value.attachments.filter(attachment => attachment.name.toLowerCase().endsWith(".pdf"));
        pdfFileList = pdfBase64List.map((pdf) => new File([base64ToBytes(pdf.content_base64!)], pdf.name, { type: pdf.mime }))
    }

    let count = {
        success: 0,
        fail: 0
    }

    for (let index = 0; index < pdfFileList.length; index++) {
        const element = pdfFileList[index];
        const formData = new FormData()
        formData.append('file', element)
        try {
            const res = await dcc.uploadEcd(formData)
            res.approved = undefined
            ecrList.value.push(res)
            count.success += 1
        } catch {
            onError()
            count.fail += 1
        } finally {

        }
    }

    const statusText = `${count.success} success, ${count.fail} fail`
    if (count.success == 0 && count.fail == 0) {
        requestEcrManual()
    } else if (ecrList.value.length > 0) {
        currentTask.value.events.SuccessEvent(statusText)
    } else {
        currentTask.value.events.ErrorEvent(statusText)
    }
}

function requestEcrManual() {
    const item = currentTask.value
    item.description = "ECR not detected in this message. Please upload manually."
    item.status = "warning"
    ecrUploadPopup.value.openModal()
}

function ecrApproveProgress() {
    const item = currentTask.value
    item.status = undefined
    item.description = "ECR approval is required: " + ecrList.value.length + " left"

    ecrList.value.forEach(ecr => {
        ecr.approved = undefined;
    });
}

function getJiraSession() {
    const item = currentTask.value
    item.description = "Waiting for Jira Session ID..."
    item.status = undefined

    const savedId = localStorage.getItem("jira>session_id") || null
    if (savedId) {
        sessionPopup.value.input = savedId
    }
    sessionPopup.value.visible = true
    sessionPopup.value.title = "Enter Jira Session ID"
    sessionPopup.value.onClick = connectJiraProgress
}

async function connectJiraProgress() {
    const item = currentTask.value
    item.description = "Connecting JIRA account..."
    try {
        userInfo.value = await dcc.checkSession(sessionPopup.value.input)
        localStorage.setItem("jira>session_id", sessionPopup.value.input)
        item.events.SuccessEvent()
    } catch (e) {
        item.events.ErrorEvent()
    } finally {
        sessionPopup.value.visible = false
    }
}

function connectJiraSuccess() {
    const item = currentTask.value
    item.status = "success"
    item.description = "Connected to JIRA account as " + userInfo.value?.displayName

    nextTask()
}

async function createJiraTaskProgress() {
    const item = currentTask.value
    item.description = "Creating JIRA task...\n"
    item.status = undefined

    try {
        for (let index = 0; index < ecrList.value.length; index++) {
            const element = ecrList.value[index]

            if (element.approved !== true) {
                createdIssueList.push("")
                continue
            }

            const payload = { ...element, "JSESSIONID": sessionPopup.value.input };
            try {
                const created = await dcc.createIssue(payload)
                //const created = { issue: "CHN-7916" } // test

                item.description += "Task created: " + created.issue + "\n"
                createdIssueList.push(created.issue)
            } catch (e) {
                item.description += `Failed while creating task for ${element.ecd_no}: ${e}\n`
                item.status = "warning"
                createdIssueList.push("")
            }
        }

        if(createdIssueList.every(item => item === "")){
            item.description += "No task was created. Cannot continue." + "\n"
            item.status = "error"
            return
        }
        
        item.events.SuccessEvent()
    } catch (e) {
        item.events.ErrorEvent()
    } finally {
        sessionPopup.value.visible = false
    }
}

function createJiraTaskSuccess() {
    const item = currentTask.value
    item.status = item.status || "success"
    item.description += "Finished successfully."

    nextTask()
}

async function addAttachmentProgress() {
    const item = currentTask.value
    item.description = "Adding attachment...\n"
    item.status = undefined

    try {
        for (let index = 0; index < createdIssueList.length; index++) {
            const createdIssue = createdIssueList[index]

            if (!createdIssue) {
                continue
            }

            const formData = new FormData()
            const file = pdfFileList[index]

            formData.append('file', file)
            formData.append('JSESSIONID', sessionPopup.value.input)
            formData.append('issue_key', createdIssue)

            await dcc.addAttachment(formData)
            item.description += `Attachment named "${file?.name}" added to ${createdIssue}.\n`
        }
        item.events.SuccessEvent()
    } catch (e) {
        item.events.ErrorEvent(e)
    } finally {
        sessionPopup.value.visible = false
    }
}

function addAttachmentSuccess() {
    const item = currentTask.value
    item.status = "success"
    item.description += "Finished successfully."

    nextTask()
}

function getJiraSubtaskList() {
    const item = currentTask.value
    item.description = "Waiting for Jira subtask selection..."
    item.status = undefined

    subtaskListPopup.value.visible = true
    subtaskListPopup.value.title = "Select Subtask List"
    subtaskListPopup.value.onClick = createJiraSubTaskProgress
}

async function createJiraSubTaskProgress() {
    subtaskListPopup.value.visible = false

    const item = currentTask.value
    loadingBar.value.show = true

    for (let index = 0; index < createdIssueList.length; index++) {
        const createdIssue = createdIssueList[index];
        const payload = {
            "JSESSIONID": sessionPopup.value.input,
            "url": createdIssue,
            "list": subtaskListPopup.value.input
        }

        item.description = `Creating Jira subtasks for ${createdIssue}...`
        loadingBar.value.status = "default"
        loadingBar.value.percentage = 0

        try {
            const res = await axios.post(`${axios.defaults.baseURL}/dcc/create_queue/`, payload)
            await new Promise<void>((resolve, reject) => {
                const eventSource = new EventSource(`${axios.defaults.baseURL}/dcc/create_subtask_stream/${res.data}`);
                eventSource.onmessage = function (event) {
                    const data = JSON.parse(event.data);
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
                        resolve()
                    }
                };
                eventSource.onerror = function (err) {
                    console.log(err)
                    loadingBar.value.status = "error"
                    eventSource.close();
                    reject()
                };
            })
        } catch (e) {
            console.log(e)
            item.events.ErrorEvent()
        } finally {
            console.log("END")
        }
        await sleep(1000)
    }

    loadingBar.value.show = false
    item.events.SuccessEvent()
}

function createJiraSubTaskSuccess() {
    const item = currentTask.value
    item.status = "success"
    item.description = "Finished successfully."

    nextTask()
}


const taskList: TaskItem[] = [
    {
        title: "Detect ECR",
        descriptions: {
            onSuccess: "ECR files found",
            onError: "Error while parsing ECR files",
        },
        events: {
            ProgressEvent: detectEcrProgress,
            SuccessEvent: detectEcrSuccess,
            ErrorEvent: onError,
        }
    },
    {
        title: "Get User Approvement",
        descriptions: {
            onSuccess: "ECR voted by user",
            onError: "Error while approving ECR",
        },
        events: {
            ProgressEvent: ecrApproveProgress,
            SuccessEvent: onSuccess,
            ErrorEvent: onError,
        }
    },
    {
        title: "Connect JIRA",
        descriptions: {
            onSuccess: "Connected to JIRA account successfully.",
            onError: "Error while connecting to JIRA. Is session ID correct?",
        },
        events: {
            ProgressEvent: getJiraSession,
            SuccessEvent: connectJiraSuccess,
            ErrorEvent: onError,
        }
    },
    {
        title: "Create Task",
        descriptions: {
            onSuccess: "JIRA task created successfully by using ECR",
            onError: "Error while creating JIRA task by using ECR",
        },
        events: {
            ProgressEvent: createJiraTaskProgress,
            SuccessEvent: createJiraTaskSuccess,
            ErrorEvent: onError,
        }
    },
    {
        title: "Add Attachment",
        descriptions: {
            onSuccess: "JIRA task created successfully by using ECR",
            onError: "Error while adding attachment to JIRA task by using ECR",
        },
        events: {
            ProgressEvent: addAttachmentProgress,
            SuccessEvent: addAttachmentSuccess,
            ErrorEvent: onError,
        }
    },
    {
        title: "Create Sub-task",
        descriptions: {
            onSuccess: "Subtasks created",
            onError: "Error while creating subtasks",
        },
        events: {
            ProgressEvent: getJiraSubtaskList,
            SuccessEvent: createJiraSubTaskSuccess,
            ErrorEvent: onError,
        }
    }
]

let interval: any
function run(message: IMsg) {
    msg.value = message
    currentTask.value = taskList[0]
    taskQueue.value.push(currentTask.value)
    currentTask.value.events.ProgressEvent()
    /* interval = setInterval(() => {
        if (taskQueue.value.length != 0) {
            taskQueue.value[taskQueue.value.length - 1].task.SuccessEvent()
        }
        if (taskList.length != taskQueue.value.length) {
            taskQueue.value.push(taskList[taskQueue.value.length])
            taskQueue.value[taskQueue.value.length - 1].task.ProgressEvent()
        } else {
            clearInterval(interval)
        }
    }, 3000) */
}

onMounted(() => {
    if (nullCheck(outlook.getMsg)) {
        window.$message.error("No msg data found")
    } else {
        run(outlook.getMsg)
    }
})

function clear() {
    taskQueue.value = []
}

defineExpose({
    run,
    clear
})

</script>

<style>
.blink {
    cursor: pointer;
    animation: blink 3s infinite ease-in-out;
}

.blink:hover {
    animation-play-state: paused;
    animation: blink 3s forwards;
}

@keyframes blink {

    0%,
    100% {
        box-shadow: 0 0 10px rgb(56, 137, 197, 1);
        opacity: 1;
    }

    50% {
        box-shadow: 0 0 5px rgb(56, 137, 197, 0.5);
        opacity: 0.8;
    }
}
</style>