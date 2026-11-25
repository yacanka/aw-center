<script setup lang="ts">
import { computed } from 'vue'
import { darkTheme, dateTrTR, NConfigProvider, NGlobalStyle, useOsTheme } from 'naive-ui'
import { resolvePreferredTheme, themeOverrides } from '@/app/services/theme'

const systemTheme = useOsTheme()
const themeName = computed(() => systemTheme.value ?? resolvePreferredTheme())
</script>

<template>
  <NConfigProvider
    :theme="themeName === 'dark' ? darkTheme : null"
    :theme-overrides="themeOverrides"
    :date-locale="dateTrTR"
  >
    <NGlobalStyle />
    <RouterView :theme-name="themeName" />
  </NConfigProvider>
</template>
