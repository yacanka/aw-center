<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft24Regular, Home24Regular, LockClosed24Regular } from '@vicons/fluent'

const route = useRoute()
const router = useRouter()
const requestedPath = computed(() =>
  typeof route.query.from === 'string' && route.query.from.startsWith('/')
    ? route.query.from.slice(0, 200)
    : ''
)

function goBack(): void {
  router.back()
}

function goHome(): void {
  void router.push({ name: 'home' })
}
</script>

<template>
  <n-result
    status="403"
    title="Access denied"
    description="Your account does not have the permission required for this workspace."
  >
    <template #icon>
      <n-icon size="120"><LockClosed24Regular /></n-icon>
    </template>
    <n-text v-if="requestedPath" depth="3">Requested destination: {{ requestedPath }}</n-text>
    <template #footer>
      <n-space justify="center">
        <n-button @click="goBack">
          <template #icon><ArrowLeft24Regular /></template>
          Go back
        </n-button>
        <n-button type="primary" @click="goHome">
          <template #icon><Home24Regular /></template>
          Home
        </n-button>
      </n-space>
    </template>
  </n-result>
</template>
