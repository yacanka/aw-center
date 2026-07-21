<template>
  <n-flex justify="center">
    <n-h1 class="gradient-text" style="margin: -12px 0 -18px">
      <strong>{{ appTitle }}</strong>
    </n-h1>
  </n-flex>
  <ActionCenter />
  <ComplianceDashboard />
</template>

<script setup lang="ts">
import ActionCenter from '@/components/ActionCenter.vue'
import ComplianceDashboard from '@/components/compdoc/ComplianceDashboard.vue'

const appTitle = import.meta.env.VITE_APP_TITLE
</script>
