<script setup lang="ts">
import { ref } from 'vue'
import { ArrowDownload24Regular } from '@vicons/fluent'
import { formatApiError } from '@/shared/api/apiError'
import { saveBlobAsFile } from '@/shared/services/download'
import { fetchDashboardExecutable } from '../api/dashboardExecutable'

const props = defineProps<{ project: string }>()
const show = ref(false)
const databasePath = ref('')
const busy = ref(false)
const error = ref('')
function setVisible(value: boolean) {
  if (busy.value) return
  databasePath.value = ''
  error.value = ''
  show.value = value
}
async function download() {
  if (!props.project || !databasePath.value.trim() || busy.value) return
  error.value = ''
  busy.value = true
  try {
    const blob = await fetchDashboardExecutable(props.project, databasePath.value)
    saveBlobAsFile(blob, 'CertificationDashboard.exe')
    show.value = false
    databasePath.value = ''
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <n-button @click="setVisible(true)" aria-haspopup="dialog">
    <template #icon><ArrowDownload24Regular aria-hidden="true" /></template>
    Download executable
  </n-button>
  <n-modal
    :show="show"
    preset="card"
    title="Download executable"
    class="dashboard-download-modal"
    :closable="!busy"
    :mask-closable="!busy"
    :close-on-esc="!busy"
    @update:show="setVisible"
  >
    <n-form @submit.prevent="download">
      <p>
        Windows okuyucusu her açılışta bu SQLite dosyasını kullanır. Dosyanın tam yolu indirilen EXE
        içine kaydedilir.
      </p>
      <n-form-item
        label="SQLite dosyasının Windows yolu"
        :label-props="{ for: 'dashboard-database-path' }"
      >
        <n-input
          v-model:value="databasePath"
          :input-props="{ id: 'dashboard-database-path', autocomplete: 'off', spellcheck: false }"
          :disabled="busy"
          placeholder="C:\AWCenter\db.sqlite3 veya \\sunucu\paylaşım\db.sqlite3"
        />
      </n-form-item>
      <n-alert v-if="error" type="error" role="alert">{{ error }}</n-alert>
      <n-flex justify="end">
        <n-button :disabled="busy" @click="setVisible(false)">Vazgeç</n-button>
        <n-button
          attr-type="submit"
          type="primary"
          :loading="busy"
          :disabled="!databasePath.trim()"
        >
          EXE indir
        </n-button>
      </n-flex>
    </n-form>
  </n-modal>
</template>

<style scoped>
:global(.dashboard-download-modal) {
  width: min(32rem, calc(100vw - 32px));
}
p {
  margin-block-start: 0;
}
.n-alert {
  margin-block-end: 16px;
}
</style>
