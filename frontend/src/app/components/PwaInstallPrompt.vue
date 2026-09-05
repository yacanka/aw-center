<script setup lang="ts">
import { ArrowDownload20Regular, Dismiss20Regular } from '@vicons/fluent'
import { onMounted, onUnmounted, ref } from 'vue'

import { usePwaInstall } from '../pwa/usePwaInstall'

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
      v-if="!error"
      size="small"
      type="primary"
      :loading="isInstalling"
      @click="handleInstall"
    >
      {{ isManualInstall ? 'How to install' : 'Install app' }}
    </n-button>
    <n-button
      quaternary
      circle
      size="small"
      title="Dismiss install suggestion"
      aria-label="Dismiss install suggestion"
      @click="dismiss"
    >
      <template #icon><Dismiss20Regular /></template>
    </n-button>
  </aside>
</template>

<style scoped>
.pwa-install-prompt {
  align-items: center;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  bottom: 24px;
  box-shadow: 0 18px 45px rgb(15 23 42 / 18%);
  display: grid;
  gap: 12px;
  grid-template-columns: auto minmax(180px, 1fr) auto auto;
  padding: 14px;
  position: fixed;
  right: 24px;
  width: min(620px, calc(100vw - 48px));
  z-index: 1000;
}

.pwa-install-icon {
  align-items: center;
  background: #0f766e;
  border-radius: 9px;
  color: #ffffff;
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
  display: grid;
  gap: 2px;
  min-width: 0;
}

.pwa-install-copy strong {
  color: #111827;
  font-size: 14px;
}

.pwa-install-copy span,
.pwa-install-copy small {
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.pwa-install-copy small {
  color: #b91c1c;
}

:global(:root[data-theme='dark']) .pwa-install-prompt {
  background: #18181c;
  border-color: #ffffff3d;
  box-shadow: 0 18px 45px rgb(0 0 0 / 42%);
}

:global(:root[data-theme='dark']) .pwa-install-copy strong {
  color: #f3f4f6;
}

:global(:root[data-theme='dark']) .pwa-install-copy span {
  color: #a1a1aa;
}

@media (max-width: 760px) {
  .pwa-install-prompt {
    bottom: 12px;
    grid-template-columns: auto 1fr auto;
    right: 12px;
    width: calc(100vw - 24px);
  }

  .pwa-install-prompt > :deep(.n-button:not([aria-label])) {
    grid-column: 1 / -1;
  }
}
</style>
