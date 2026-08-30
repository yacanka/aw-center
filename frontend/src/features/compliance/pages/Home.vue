<template>
  <n-flex justify="center">
    <n-h1 class="gradient-text" style="margin: -12px 0 -18px">
      <strong>Compliance Docs</strong>
    </n-h1>
  </n-flex>
  <ComplianceDashboard />
</template>

<script setup lang="ts">
import ComplianceDashboard from '@/features/compliance/components/ComplianceDashboard.vue'
</script>
