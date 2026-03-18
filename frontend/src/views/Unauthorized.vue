<script setup lang="ts">
import { h, ref, onMounted, watch } from 'vue'
import { NButton, NDataTable, NSpace, NTag, NSpin, NUpload } from 'naive-ui'
import { useRouter } from 'vue-router'
import {LockClosed24Regular, ArrowLeft24Regular} from '@vicons/fluent';

const router = useRouter()

function goBack(){
  router.go(-1)
}

</script>

<template>
  <n-result status="401" title="401 Unauthorized" description="Can't touch this.">
    <template #icon>
      <n-icon size=144>
        <LockClosed24Regular />
      </n-icon>
    </template>

    <template #footer>
      <n-button @click="goBack">
        <template #icon>
          <ArrowLeft24Regular />
        </template>
        Go Back
      </n-button>
    </template>
  </n-result>
</template>