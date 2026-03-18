<script setup lang="ts">
import { ref } from 'vue'
import { usePptxStore } from '@/stores/api'
import { useMessage, NUpload, NUploadDragger, NIcon, NButton, NInput, UploadCustomRequestOptions } from 'naive-ui'
import { CloudArrowUp24Regular as UploadIcon } from '@vicons/fluent'

const msg = useMessage()
const title = ref('')
const store = usePptxStore()

async function handleUploadReq({ file, onFinish, onError }: UploadCustomRequestOptions) {
    if (!file.file) return

    const form = new FormData()
    form.append('title', title.value || file.name.replace(/\.pptx?$/i, ''))
    form.append('file', file.file)
    
    try {
        const data = await store.uploadPresentation(form)
        onFinish()
        window.$loadingBar.finish()
        msg.success('Uploaded and converted')
        emit('uploaded', { id: data.id, title: data.title })
    } catch (err) {
        console.error(err)
        onError()
        window.$loadingBar.error()
    }

    store.fetchPresentations()
}

const emit = defineEmits<{ (e: 'uploaded', p: { id: number, title: string }): void }>()
</script>

<template>
    <n-space vertical>
        <n-input v-model:value="title" placeholder="Presention title (optional)" />
        <n-upload directory-dnd :custom-request="handleUploadReq" :show-file-list="false" accept=".pptx" :disabled="store.isLoading">
            <n-upload-dragger>
                <div>
                    <n-icon size="48">
                        <UploadIcon />
                    </n-icon>
                    <div v-if="store.isLoading">Please wait while presentation is saving...</div>
                    <div v-else="store.isLoading">Click or drag a file to this area to upload</div>
                </div>
            </n-upload-dragger>
        </n-upload>
    </n-space>
</template>