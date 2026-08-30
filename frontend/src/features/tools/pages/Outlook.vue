<script setup lang="ts">
import { h, ref } from 'vue'
import { NUpload, NUploadDragger, NButton, NCard, NDataTable } from 'naive-ui'
import type { NotificationType } from 'naive-ui'
import { useRouter } from 'vue-router'
import { IAttachment, IMsg } from '@/features/tools/models/outlook'
import { saveBlobAsFile } from '@/shared/services/download'
import { downloadOutlookAttachmentBlob } from '@/features/tools/api/outlookAttachmentFiles'
import { parseOutlookMessage } from '@/features/tools/api/outlookMessages'

const router = useRouter()
const fileList = ref<any[]>([])
const msg = ref<null | IMsg>(null)
const taskStatus = ref<{
  visible: boolean
  title: string
  status: NotificationType | ''
  description: string
  module: string
}>({
  visible: false,
  title: '',
  status: '',
  description: '',
  module: ''
})

const columns = [
  { title: 'Name', key: 'name' },
  {
    title: 'Size',
    key: 'size',
    render: (row: IAttachment) => `${(row.size / 1024).toFixed(1)} KB`
  },
  { title: 'MIME', key: 'mime' },
  {
    title: 'Actions',
    key: 'action',
    render: (row: IAttachment) => {
      if (row.download_capability) {
        return h(
          NButton,
          { text: true, type: 'primary', onClick: () => download(row) },
          () => 'Download'
        )
      }
      return '—'
    }
  }
]

function classifyWithMsgSubject(str: string) {
  if (!str || typeof str !== 'string') return null

  const rules = [
    {
      regex: /crb\s+\d+/i, // regex: /^[a-zçğıöşü]+\s+crb+\s+\d+\s+call$/i,
      module: 'ecrTask',
      label: 'CRB CALL detected',
      message:
        'Open the server-owned ECR workflow to review the PDF snapshot, approve the publication plan, and follow its durable JIRA job.'
    }
  ]

  for (const rule of rules) {
    if (rule.regex.test(str.trim())) {
      return {
        matched: true,
        module: rule.module,
        label: rule.label,
        description: rule.message,
        original: str.trim()
      }
    }
  }

  return null
}

function runMailTask(message: IMsg) {
  const classified = classifyWithMsgSubject(message.mail.subject)
  if (classified) {
    taskStatus.value.status = 'success'
    taskStatus.value.title = classified.label
    taskStatus.value.description = classified.description
    taskStatus.value.module = classified.module
  } else {
    window.$message.warning('Unknown mail task')
  }
}

async function download(attachment: IAttachment): Promise<void> {
  if (!attachment.download_capability) return
  try {
    saveBlobAsFile(await downloadOutlookAttachmentBlob(attachment), attachment.name)
  } catch {
    window.$message.error('The private attachment link is unavailable or expired.')
  }
}

async function sendFile() {
  taskStatus.value.status = ''
  if (fileList.value.length === 0) {
    window.$message.warning('Önce .msg dosyası seçin.')
    return
  }
  const file = fileList.value[0].file as File
  const fd = new FormData()
  fd.append('file', file)

  try {
    window.$loadingBar.start()
    const res = await parseOutlookMessage(fd)
    msg.value = res
    runMailTask(res)
  } catch (e: any) {
    window.$message.error('The Outlook message could not be read safely.')
    window.$loadingBar.error()
  } finally {
    window.$loadingBar.finish()
  }
  fileList.value = []
}

function handleItemHeaderClick() {}
</script>

<template>
  <div>
    <n-alert
      v-show="taskStatus.status != ''"
      :title="taskStatus.title"
      :type="taskStatus.status"
      closable
    >
      <n-text> {{ taskStatus.description }} </n-text>
      <n-flex justify="center" style="margin: 8px">
        <n-button
          v-if="taskStatus.status == 'success'"
          @click="router.push({ name: taskStatus.module })"
        >
          Start Task
        </n-button>
      </n-flex>
    </n-alert>
    <n-card title="Upload MSG file and Parse">
      <NUpload
        v-model:file-list="fileList"
        accept=".msg"
        :max="1"
        :show-file-list="true"
        :custom-request="sendFile"
        :default-upload="true"
      >
        <NUploadDragger> Click or drag .msg file to this area to upload </NUploadDragger>
      </NUpload>
    </n-card>

    <n-card v-if="msg" title="Mail Info">
      <div>
        <div><b>Subject:</b> {{ msg.mail.subject }}</div>
        <div><b>From:</b> {{ msg.mail.sender }}</div>
        <n-flex class="mail-address-row">
          <b>To:</b>
          <div class="mail-address app-long-content">{{ msg.mail.to }}</div>
        </n-flex>
        <n-flex class="mail-address-row">
          <b>CC:</b>
          <div class="mail-address app-long-content">{{ msg.mail.cc }}</div>
        </n-flex>
        <div><b>Date:</b> {{ msg.mail.date }}</div>
      </div>
      <div v-if="msg.mail.body_plain">
        <n-collapse @item-header-click="handleItemHeaderClick" arrow-placement="right">
          <n-collapse-item title="Body" name="body" display-directive="if">
            <n-card>
              <pre class="app-preformatted">{{ msg.mail.body_plain }}</pre>
            </n-card>
          </n-collapse-item>
        </n-collapse>
      </div>
    </n-card>

    <n-card v-if="msg" title="Attachments">
      <NDataTable :columns="columns" :data="msg.attachments" :bordered="false" :scroll-x="720" />
    </n-card>
  </div>
</template>

<style scoped>
pre {
  background: #f6f6f6;
  padding: 8px;
  border-radius: 6px;
}

.mail-address-row {
  align-items: flex-start;
  flex-wrap: nowrap;
  margin-block: 6px;
  min-width: 0;
}

.mail-address {
  flex: 1;
  max-height: 100px;
  overflow: auto;
}
</style>
