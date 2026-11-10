<script setup lang="ts">
import { ArrowDownload20Regular, Dismiss20Regular } from '@vicons/fluent'
import { NIcon, useThemeVars } from 'naive-ui'
import { onMounted, onUnmounted, ref } from 'vue'

import { usePwaInstall } from '../pwa/usePwaInstall'

const themeVars = useThemeVars()
const showManualInstructions = ref(false)
const { shouldShow, isManualInstall, isInstalling, error, start, stop, dismiss, requestInstall } =
  usePwaInstall()

async function handleInstall(): Promise<void> {
  if (isManualInstall.value) {
    showManualInstructions.value = true
    return
  }
  await requestInstall()
}

onMounted(start)
onUnmounted(stop)
</script>

<template>
  <aside v-if="shouldShow" class="pwa-install-prompt" aria-live="polite">
    <div class="pwa-install-icon" aria-hidden="true"><ArrowDownload20Regular /></div>
    <div class="pwa-install-copy">
      <strong>Install AW Center</strong>
      <span v-if="showManualInstructions">
        Open Safari's Share menu and select “Add to Home Screen”.
      </span>
      <span v-else>Access the app quickly from your device in a standalone window.</span>
      <small v-if="error">{{ error }}</small>
    </div>
    <n-button
      class="pwa-install-action"
      v-if="!error"
      size="small"
      type="primary"
      :loading="isInstalling"
      @click="handleInstall"
    >
      {{ isManualInstall ? 'How to install' : 'Install app' }}
    </n-button>
    <n-button
      class="pwa-install-dismiss"
      quaternary
      circle
      size="small"
      title="Dismiss install suggestion"
      aria-label="Dismiss install suggestion"
      @click="dismiss"
    >
      <template #icon><n-icon :component="Dismiss20Regular" /></template>
    </n-button>
  </aside>
</template>

<style scoped>
.pwa-install-prompt {
  align-items: center;
  background: v-bind('themeVars.popoverColor');
  border: 1px solid v-bind('themeVars.borderColor');
  border-radius: 10px;
  bottom: max(40px, env(safe-area-inset-bottom));
  box-shadow: v-bind('themeVars.boxShadow2');
  display: grid;
  gap: 12px;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  grid-template-areas: 'icon copy action dismiss';
  padding: 14px;
  max-height: calc(100dvh - 64px);
  overflow-y: auto;
  font-family: v-bind('themeVars.fontFamily');
  position: fixed;
  right: 24px;
  width: min(620px, calc(100vw - 48px));
  z-index: 1000;
}

.pwa-install-icon {
  grid-area: icon;
  align-items: center;
  background: v-bind('themeVars.primaryColor');
  border-radius: 9px;
  color: v-bind('themeVars.baseColor');
  display: flex;
  height: 40px;
  justify-content: center;
  width: 40px;
}

.pwa-install-icon svg {
  height: 22px;
  width: 22px;
}

.pwa-install-copy {
  grid-area: copy;
  overflow-wrap: anywhere;
  display: grid;
  gap: 2px;
  min-width: 0;
}

.pwa-install-copy strong {
  color: v-bind('themeVars.textColor1');
  font-size: 14px;
}

.pwa-install-copy span,
.pwa-install-copy small {
  color: v-bind('themeVars.textColor2');
  font-size: 12px;
  line-height: 1.4;
}

.pwa-install-copy small {
  color: v-bind('themeVars.errorColor');
}

.pwa-install-action {
  grid-area: action;
}

.pwa-install-dismiss {
  grid-area: dismiss;
  align-self: start;
}

@media (max-width: 760px) {
  .pwa-install-prompt {
    gap: 10px;
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas:
      'icon copy dismiss'
      'action action action';
    right: 12px;
    width: calc(100vw - 24px);
  }
}
</style>
