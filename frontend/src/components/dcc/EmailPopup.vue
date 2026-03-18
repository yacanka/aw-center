<template>
  <n-modal v-model:show="showModal" preset="dialog" title="Send Email" centered>
    <n-space vertical>
      <n-text>It will be sent to assignees who have not closed their subtasks.</n-text>
      <n-input v-model:value="mailReq.issue" disabled />
      <n-input-number v-model:value="mailReq.ccb_no" placeholder="Enter CCB No" />
      <n-date-picker v-model:formatted-value="mailReq.due_date" type="date" format="dd.MM.yyyy" :firstDayOfWeek="0" />
    </n-space>
    <template #action>
      <n-button type="info" ghost @click="sendMail">Send</n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { IDcc } from '@/models/dcc'
import { NModal } from 'naive-ui';

const showModal = ref(false);
const mailReq = ref({
  issue: "",
  ccb_no: null,
  due_date: null,
  JSESSIONID: ""
})

onMounted(() => {
  const storedSessionID = localStorage.getItem("jira>session_id")
  mailReq.value.JSESSIONID = storedSessionID ? storedSessionID : ""
});

async function sendMail() {
  window.$loadingBar.start()
  try {
    await window.$dccStore.sendMail(mailReq.value)
    window.$loadingBar.finish()
  } catch (err) {
    window.$loadingBar.error()
  }

  closeModal()
}

function openModal(value: IDcc) {
  mailReq.value.issue = value.issue
  showModal.value = true
}

function closeModal() {
  showModal.value = false;
}

defineExpose({
  openModal
})
</script>

<style scoped></style>
