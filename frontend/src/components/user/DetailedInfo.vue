<template>
  <n-space vertical justify="space-around"> {{ props.user?.id }} Still In Development </n-space>
</template>

<script setup lang="ts">
const props = defineProps(['user'])
</script>
