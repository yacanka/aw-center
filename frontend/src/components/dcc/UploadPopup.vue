<template>
  <n-modal v-model:show="showModal" preset="dialog" title="Add New DCC" centered width="500px">
    <div class="modal-content">
      <n-tabs type="card" placement="top">
        <n-tab-pane name="url" tab="Via Url Address">
          <n-input v-model:value="url" type="url" placeholder="Enter URL" />
          <n-flex justify="end" style="margin-top: 12px">
            <n-button @click="addViaUrl">Add</n-button>
          </n-flex>
        </n-tab-pane>
        <n-tab-pane name="file" tab="Via File Upload">
          <n-upload directory-dnd :show-file-list="false" :max="1" accept=".pdf" :custom-request="handleUploadReq"
            @change="handleChange">
            <n-upload-dragger>
              <n-text style="font-size: 16px">
                Click or drag a file to this area to upload
              </n-text>
              <n-p depth="3" style="margin: 8px 0 0 0">
                {{ props.title }}
              </n-p>
            </n-upload-dragger>
          </n-upload>
          <n-flex justify="center" style="margin: 12px 0 0 0">
            {{ props.description }}
          </n-flex>
        </n-tab-pane>
      </n-tabs>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { NModal, UploadCustomRequestOptions } from 'naive-ui';
import axios from 'axios'
import { IDcc } from '@/models/dcc';
import { IEcd } from '@/models/ecd';


const showModal = ref(false);
const url = ref("")

const uploaderFormRef = ref(null); // UploadForm'a erişim için

onMounted(() => {
});

async function addViaUrl() {
  const sessionId = localStorage.getItem("jira>session_id")
  try{
    const data: IDcc = await window.$dccStore.addDcc({ url: url.value, JSESSIONID: sessionId })
    props.onAddSuccess?.(data)
  }catch(err: any){
    //window.$message.error("Error while adding url.")
  }
}

function setActive(show: boolean) {
  url.value = ""
  showModal.value = show
}

function handleChange() {
  window.$loadingBar.start()
}

const props = defineProps<{
  uploadUrl: string
  description: string
  title: string
  onUploadSuccess?: (data: IEcd) => void
  onAddSuccess?: (data: IDcc) => void
  onError?: () => void
}>()

function handleUploadReq({ file, onFinish, onError }: UploadCustomRequestOptions) {
  if (!file.file) return
  const formData = new FormData()
  formData.append('file', file.file)
  axios.post(props.uploadUrl, formData).then((res) => {
    onFinish()
    window.$notification.success({
      title: 'Success',
      description: 'ECR read successfully.',
      duration: 3000
    })
    window.$loadingBar.finish()
    props.onUploadSuccess?.(res.data)
  }).catch((err) => {
    onError()
    window.$notification.error({
      title: 'Error',
      description: err.response.data.message,
      duration: 3000
    })
    window.$loadingBar.error()
  }).finally(() => {
    setActive(false)
  })
}

defineExpose({
  setActive
})
</script>

<style scoped></style>
