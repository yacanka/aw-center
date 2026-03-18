<template>
  <n-modal v-model:show="showUploadModal" preset="dialog" title="Attempt the ECR Assessment" centered width="500px">
    <div class="modal-content">
      <n-upload directory-dnd :show-file-list="false" :max="1" accept=".pdf" :custom-request="handleUploadReq">
        <n-upload-dragger>
          <n-text style="font-size: 16px">
            Click or drag a ECR to this area to upload
          </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0">
            Read ECR file
          </n-p>
        </n-upload-dragger>
      </n-upload>
      <n-flex justify="center" style="margin: 12px 0 0 0">
        After that, you can check ECR information and approve.
      </n-flex>
    </div>
  </n-modal>
  <n-modal v-model:show="showAnalyzeModal" :mask-closable="false" preset="card" title="Document Assessment"
    transform-origin="center" :on-after-leave="reset" :style="{ width: '60%', minWidth: '600px' }">
    <n-space vertical>
      <n-flex v-if="loading">
        <n-spin size="small" />
        <h3>Analyzing...</h3>
      </n-flex>

      <n-skeleton v-if="loading" text :repeat="9" />
      <n-space v-else vertical>
        <n-card v-for="(assessment, index) in assessments" :key="index">
          {{ assessment }}
        </n-card>
      </n-space>
      <n-flex justify="center">
        <n-button type="success" ghost @click="reset">Ok</n-button>
      </n-flex>
    </n-space>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { NModal, UploadCustomRequestOptions } from 'naive-ui';
import axios from 'axios';
import { IEcd } from '@/models/ecd';

const assessments = ref<IEcd[]>()
const loading = ref()

const showUploadModal = ref(false)
const showAnalyzeModal = ref(false)

function handleUploadReq({ file, onFinish, onError }: UploadCustomRequestOptions) {
  if(!file.file) return
  const formData = new FormData()
  formData.append('file', file.file)
  axios.post(axios.defaults.baseURL+'/dcc/upload/', formData).then((res)=>{
    onFinish()
    window.$notification.success({
      title: 'Success',
      description: 'ECR read successfully.',
      duration: 3000
    })
    window.$loadingBar.finish()
    openAnalyze(res.data)
  }).catch(()=>{
    onError()
    window.$notification.error({
      title: 'Error',
      description: 'Error while reading ECR.',
      duration: 3000
    })    
    window.$loadingBar.error()
  }).finally(()=>{
    showUploadModal.value = false;
  })
}

function openUpload(){
  showUploadModal.value = true;
}

async function openAnalyze(data: IEcd) {
  loading.value = true
  showAnalyzeModal.value = true;
  assessments.value = await window.$dccStore.ecdAssessment(data)
  loading.value = false
}

function reset(){
  showUploadModal.value = false;
  showAnalyzeModal.value = false;
}

defineExpose({ openUpload })

onMounted(() => {

});
</script>
