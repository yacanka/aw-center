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
            type="primary"
            ghost
            style="width: 100%; margin-bottom: 8px"
            :loading="fieldLoading"
            :disabled="nullCheck(generator.url)"
            @click="loadSubtaskFields"
            >Load Fields</n-button
          >
          <n-button
            type="info"
            ghost
            style="width: 100%"
            :disabled="checkGenerateStatus()"
            @click="createSubtasks"
            >Generate</n-button
          >
        </n-grid-item>
        <n-grid-item span="6">
          <n-ellipsis style="margin: 0px 0px -12px 0px">
            {{ loadingBar.content }}
          </n-ellipsis>
        </n-grid-item>
        <n-grid-item span="6" v-if="loadingBar.show">
          <n-progress
            type="line"
            :status="loadingBar.status"
            :percentage="loadingBar.percentage"
            indicator-placement="outside"
            :height="30"
            :processing="loadingBar.status == 'default' ? true : false"
          >
          </n-progress>
        </n-grid-item>
        <n-grid-item span="1">
          <n-checkbox
            v-model:checked="duedateField.include"
            :focusable="false"
            @update:checked="handleDuedateCheckbox"
            style="margin-bottom: 4px"
            >Add due date :</n-checkbox
          >
          {{ dateDaysOffset(duedateField.days) }}
          <n-input-number
            v-model:value="duedateField.days"
            size="tiny"
            placeholder="Enter day offset"
            :disabled="!duedateField.include"
            min="0"
            @update:value="handleDuedateNumber"
          />
        </n-grid-item>
        <n-grid-item span="6">
          <subtask-list v-model:list="generator.list" :fields="subtaskFields" />
        </n-grid-item>
      </n-grid>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { createAuthenticatedEventSource } from '@/services/eventSource'
import { useOrgsStore } from '@/stores/api'
import SubtaskList from '@/components/jira/SubtaskList.vue'
import { toTitleCase } from '@/utils/text'
import { NotificationType } from 'naive-ui'
import { dateDaysOffset } from '@/utils/time'
import { nullCheck } from '@/utils/general'
import { IJiraField } from '@/models/jira'
import { formatApiError } from '@/services/apiError'

type Generator = {
  JSESSIONID: string
  url: string
  list: Array<any>
  duedate?: number
}

const orgstore = useOrgsStore()
const generator = ref({} as Generator)
const subtaskFields = ref<IJiraField[]>([])
const fieldLoading = ref(false)

const loadingBar = ref({
  show: true,
  status: '',
  percentage: 0,
  content: ''
})

const duedateField = ref({
  include: false,
  days: 0
})

type StreamData = {
  status: string
  type: string
  percentage: number
  content: any
}

const handleDuedateCheckbox = (checked: boolean) => {
  if (checked) {
    generator.value.duedate = duedateField.value.days
  } else {
    delete generator.value.duedate
  }
}

const handleDuedateNumber = (value: number) => {
  generator.value.duedate = value
}

const checkGenerateStatus = () => {
  return (
    loadingBar.value.status == 'default' ||
    nullCheck(generator.value.url) ||
    subtaskFields.value.length == 0 ||
    (duedateField.value.include && duedateField.value.days == null)
  )
}

function loadSubtaskFields() {
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
  loadingBar.value.show = true
  loadingBar.value.status = 'default'
  loadingBar.value.percentage = 0

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

onMounted(() => {
  const storedSessionID = localStorage.getItem('jira>session_id')
  generator.value.JSESSIONID = storedSessionID ? storedSessionID : ''

  if (orgstore.getPeople.length == 0) {
    orgstore.fetchPeople()
  }
})
</script>
