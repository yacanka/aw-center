<template>
  <n-config-provider :theme="useUserStore().getPreferences.theme == 'dark' ? darkTheme : lightTheme">
    <n-dialog-provider>
      <n-message-provider>
        <n-notification-provider>
          <n-loading-bar-provider>
            <MainView />
          </n-loading-bar-provider>
        </n-notification-provider>
      </n-message-provider>
    </n-dialog-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { darkTheme, lightTheme } from 'naive-ui'
import MainView from '@/views/MainView.vue'
import { useUserStore } from './stores/user'

</script>

<style>
body,
html {
  margin: 0;
  padding: 0;
  transition: background-color 100s ease
}
</style>
