<template>
  <n-flex justify="center">
    <n-card title="JIRA Subtask Generator" style="width: 90%; min-width: 300px">
      <n-grid cols="6" x-gap="12" y-gap="18">
        <n-grid-item span="5">
          <n-input
            v-model:value="generator.url"
            type="url"
            placeholder="Enter Url"
            @keydown.enter.prevent
          />
        </n-grid-item>
        <n-grid-item span="1">
          <n-button
            type="info"
            ghost
            style="width: 100%"
            :disabled="checkGenerateStatus()"
            @click="createSubtasks"
            >Generate</n-button
          >
        </n-grid-item>
        <n-grid-item v-if="loadingBar.show" span="6">
          <n-flex vertical size="small" class="subtask-progress">
            <n-ellipsis v-if="loadingBar.content">
              {{ loadingBar.content }}
            </n-ellipsis>
            <n-progress
              type="line"
              :status="loadingBar.status"
              :percentage="loadingBar.percentage"
              indicator-placement="outside"
              :height="30"
              :processing="loadingBar.status == 'default'"
            />
          </n-flex>
        </n-grid-item>
        <n-grid-item span="6">
          <subtask-list
            v-model:list="generator.list"
            :fields="subtaskFields"
            :field-loading="fieldLoading"
            :field-load-disabled="isFieldLoadDisabled"
            @load-fields="loadSubtaskFields"
          />
        </n-grid-item>
      </n-grid>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import axios from 'axios'
import { createAuthenticatedEventSource } from '@/services/eventSource'
import SubtaskList from '@/components/jira/SubtaskList.vue'
import { toTitleCase } from '@/utils/text'
import { NotificationType } from 'naive-ui'
import { nullCheck } from '@/utils/general'
import { IJiraField } from '@/models/jira'
import { formatApiError } from '@/services/apiError'
import { useDccStore } from '@/stores/dcc'

type Generator = {
  JSESSIONID: string
  url: string
  list: Array<any>
}

const dccStore = useDccStore()
const generator = ref({} as Generator)
const subtaskFields = ref<IJiraField[]>([])
const fieldLoading = ref(false)

const loadingBar = ref({
  show: false,
  status: '',
  percentage: 0,
  content: ''
})

type StreamData = {
  status: string
  type: string
  percentage: number
  content: any
}

const isUrlEmpty = computed(() => nullCheck(generator.value.url))
const isFieldLoadDisabled = computed(() => isUrlEmpty.value || fieldLoading.value)

const checkGenerateStatus = () => {
  return loadingBar.value.status == 'default' || isUrlEmpty.value
}

function loadSubtaskFields() {
  if (isFieldLoadDisabled.value) return
  generator.value.JSESSIONID = dccStore.getSessionId
  fieldLoading.value = true
  axios
    .post(`${axios.defaults.baseURL}/dcc/subtask_fields/`, {
      JSESSIONID: generator.value.JSESSIONID,
      url: generator.value.url
    })
    .then((res) => {
      subtaskFields.value = res.data.fields
      window.$notification.success({
        title: 'Fields Loaded',
        description: `${res.data.issue} sub-task fields are ready.`,
        duration: 3000
      })
    })
    .catch((err) => {
      subtaskFields.value = []
      window.$notification.error({
        title: 'Field Load Error',
        description: formatApiError(err),
        duration: 5000
      })
    })
    .finally(() => {
      fieldLoading.value = false
    })
}

function createSubtasks() {
  generator.value.JSESSIONID = dccStore.getSessionId
  loadingBar.value.show = true
  loadingBar.value.status = 'default'
  loadingBar.value.percentage = 0
  loadingBar.value.content = 'Preparing subtask creation...'

  axios
    .post(`${axios.defaults.baseURL}/dcc/create_queue/`, generator.value)
    .then((res) => {
      const eventSource = createAuthenticatedEventSource(`/dcc/create_subtask_stream/${res.data}`)
      eventSource.onmessage = function (event) {
        const data: StreamData = JSON.parse(event.data)
        console.log(data)
        if (data.status == 'progress') {
          loadingBar.value.percentage = data.percentage
          loadingBar.value.content = `Creating ${data.content}...`
        } else if (['success', 'warning', 'error'].includes(data.status)) {
          eventSource.close()
          loadingBar.value.percentage = 100
          loadingBar.value.status = data.status
          loadingBar.value.content = ''
          window.$notification[data.status as NotificationType]({
            title: toTitleCase(data.status),
            description: data.content,
            duration: 3000
          })
        }
      }
      eventSource.onerror = function (err) {
        console.log(err)
        loadingBar.value.status = 'error'
        eventSource.close()
      }
    })
    .catch((err) => {
      console.error(err)
      window.$notification.error({
        title: 'Error',
        description: `Error while uploading file: ${formatApiError(err)}`
      })
    })
    .finally(() => {
      console.log('END')
    })
}
</script>

<style scoped>
.subtask-progress {
  margin-top: -8px;
}
</style>
