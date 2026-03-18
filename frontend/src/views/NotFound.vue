<script setup lang="ts">
import { h, ref, onMounted, onUnmounted, watch } from 'vue'
import { NButton, NDataTable, NSpace, NTag, NSpin, NUpload } from 'naive-ui'
import { useRouter } from 'vue-router'
import {Search24Regular} from '@vicons/fluent';


const router = useRouter()
const timerElement = ref(5)
let countdownInterval: any = null
onMounted(()=>{
  countdownInterval = setInterval(() => {
    timerElement.value = timerElement.value - 1;
    if (timerElement.value < 0) {
      clearInterval(countdownInterval);
      router.push({name: "login"})
    }
  }, 1000);
})

onUnmounted(() => {
  clearInterval(countdownInterval)
})
</script>

<template>
  <n-result status="404" title="404 Not Found" description="You are lost.">
    <template #icon>
      <n-icon size=144>
        <Search24Regular />
      </n-icon>
    </template>

    <template #footer>
      You will be redirected to the homepage in {{ timerElement }} seconds.
    </template>
  </n-result>
</template>