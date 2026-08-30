<template>
  <n-modal
    v-model:show="popup.visible"
    preset="card"
    :title="popup.title"
    class="app-modal"
    :mask-closable="popup.closable"
    transform-origin="center"
  >
    <n-scrollbar style="max-height: 80vh; padding-right: 16px">
      <div v-if="popup.text_content" class="popup-content app-long-content">
        <p style="white-space: pre-line">{{ popup.text_content }}</p>
      </div>
      <n-space v-if="popup.list_content">
        <n-card v-for="(item, index) in popup.list_content" :key="index">
          {{ item }}
        </n-card>
      </n-space>
    </n-scrollbar>
    <n-flex justify="center" style="margin-top: 10px">
      <n-button type="info" @click="closeModal">Ok</n-button>
    </n-flex>
  </n-modal>
</template>

<style scoped>
.popup-content {
  padding: clamp(12px, 3vw, 20px);
}
</style>

<script setup>
import { popupStore } from '@/app/stores/popupStore'
const popup = popupStore()

function closeModal() {
  popup.close()
}
</script>
