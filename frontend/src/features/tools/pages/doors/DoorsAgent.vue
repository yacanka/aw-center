<template>
  <n-space vertical size="large">
    <n-card title="IBM Rational DOORS Agent">
      <n-space vertical>
        <n-text>Deneme görevi: ATA chapter–panel tutarlılığı</n-text>
        <n-text depth="3">
          Modüldeki attribute’ları bulur, ATA chapter değerlerini karşılaştırır ve bir chapter’ın
          birden fazla panele bağlandığı durumları bildirir. DOORS verileri değiştirilmez.
        </n-text>
        <n-alert :type="worker?.available ? 'success' : 'warning'" :bordered="false">
          {{ readinessMessage }}
        </n-alert>
      </n-space>
      <n-form label-placement="top" style="margin-top: 16px" @submit.prevent="queueCheck">
        <n-form-item label="Modül yolu">
          <n-input
            v-model:value="modulePath"
            placeholder="/Project/System Requirements"
            :disabled="active || queueing"
          />
        </n-form-item>
        <n-space>
          <n-button type="primary" :loading="queueing" :disabled="!canQueue" @click="queueCheck">
            Kalite kontrolünü başlat
          </n-button>
          <n-button :loading="statusLoading" @click="loadStatus">Worker durumunu yenile</n-button>
        </n-space>
      </n-form>
      <n-text depth="3">
        En fazla 10.000 obje ve 50 attribute taranır; sınır aşılırsa sonuç eksik olarak işaretlenir.
        ATA 27-10-00, chapter 27 olarak değerlendirilir. Panel adlarında yalnızca harf büyüklüğü ve
        boşluk farkları tolere edilir.
      </n-text>
    </n-card>

    <n-alert v-if="errorMessage || lastError" type="error">
      {{ errorMessage || lastError }}
      <n-button v-if="errorMessage" @click="refresh()">İş durumunu yeniden yükle</n-button>
    </n-alert>
    <PageJobStatus
      :job="job"
      :cancelling="cancelling"
      :downloading="downloading"
      @cancel="cancel"
      @download="download"
      @open="openJobCenter"
    />

    <n-card v-if="job" title="Kontrol adımları">
      <n-space vertical>
        <n-text aria-live="polite">{{ job.message }}</n-text>
        <n-flex v-for="(step, index) in steps" :key="step.progress" align="center">
          <n-tag size="small">{{ index + 1 }}</n-tag>
          <n-text>{{ step.label }}</n-text>
          <n-tag size="small" :type="stepType(step.progress, steps[index + 1]?.progress)">
            {{ stepLabel(step.progress, steps[index + 1]?.progress) }}
          </n-tag>
        </n-flex>
        <n-text depth="3">Durum worker bildirimlerinden yaklaşık 2 saniyede bir yenilenir.</n-text>
        <n-alert v-if="job.error_code" type="error" :title="job.error_code">{{
          job.message
        }}</n-alert>
      </n-space>
    </n-card>

    <n-card v-if="job?.status === 'succeeded'" title="Kalite kontrolü sonucu">
      <n-space vertical>
        <n-text v-if="resultLoading">Rapor yükleniyor…</n-text>
        <n-alert v-if="resultError" type="error">
          {{ resultError }}
          <n-button :loading="resultLoading" @click="loadResult(job)"
            >Raporu yeniden yükle</n-button
          >
        </n-alert>
        <template v-if="result">
          <n-alert :type="result.outcome === 'passed' ? 'success' : 'warning'" :title="resultTitle">
            {{ result.summary.conflicting_chapters }} ATA chapter birden fazla panele bağlı.
            {{ result.summary.finding_count }} bulgu tespit edildi.
          </n-alert>
          <n-text>Modül: {{ result.module_path }}</n-text>
          <n-text>
            {{ result.summary.scanned_objects }} obje okundu ·
            {{ result.summary.checked_objects }} obje değerlendirildi ·
            {{ result.summary.chapters }} chapter karşılaştırıldı
          </n-text>
          <n-alert v-if="!result.complete" type="warning">
            Kontrol kapsamı eksik. Bu rapor modülün tamamının tutarlı olduğunu doğrulamaz.
            {{ result.summary.unassigned_objects }} objede iki alan da boş;
            {{ result.summary.unresolved_objects }} objede değerler eksik veya belirsiz.
          </n-alert>
          <n-button :aria-expanded="showDetails" @click="showDetails = !showDetails">
            {{ showDetails ? 'Detayları gizle' : 'Detaylar' }}
          </n-button>
          <template v-if="showDetails">
            <n-text v-for="(attribute, role) in result.attributes" :key="role">
              {{ role === 'ata' ? 'ATA chapter attribute' : 'Panel attribute' }}:
              {{ attribute.name || 'Seçilemedi' }} ({{ methodLabel(attribute.method) }}) · Adaylar:
              {{ attribute.candidates.join(', ') || 'Bulunamadı' }}
            </n-text>
            <n-alert v-for="warning in result.warnings" :key="warning" type="warning">{{
              warning
            }}</n-alert>
            <n-alert v-if="result.summary.omitted_findings" type="warning">
              İlk {{ result.findings.length }} bulgu gösteriliyor.
              {{ result.summary.omitted_findings }} ek bulgu rapor sınırı nedeniyle listelenmedi.
            </n-alert>
            <n-card
              v-for="(finding, index) in result.findings"
              :key="index"
              size="small"
              embedded
              :title="finding.chapter ? `ATA ${finding.chapter}` : `Bulgu ${index + 1}`"
            >
              <n-space vertical>
                <n-text>{{ finding.message }}</n-text>
                <n-text v-if="finding.panels.length"
                  >Paneller: {{ finding.panels.join(', ') }}</n-text
                >
                <n-text>Öneri: {{ finding.suggestion }}</n-text>
                <n-text v-for="(item, itemIndex) in finding.evidence" :key="itemIndex">
                  Obje {{ item.absolute_number }} ({{ item.identifier }}) · ATA:
                  {{ item.ata_value || 'Boş' }} · Panel: {{ item.panel_value || 'Boş' }}
                </n-text>
                <n-text v-if="finding.evidence_count > finding.evidence.length" depth="3">
                  {{ finding.evidence_count }} kaydın ilk {{ finding.evidence.length }} örneği
                  gösteriliyor.
                </n-text>
              </n-space>
            </n-card>
            <n-text v-if="job.events?.length" depth="3">Worker işlem geçmişi</n-text>
            <n-text v-for="event in job.events" :key="event.id" depth="3">
              {{ new Date(event.created_at).toLocaleTimeString() }} · {{ event.message }}
            </n-text>
          </template>
        </template>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { formatApiError } from '@/shared/api/apiError'
import { fetchDoorsStatus, type DoorsStatus } from '@/features/integrations/api/doorsAutomation'
import {
  enqueueDoorsQualityCheck,
  fetchDoorsQualityResult,
  type DoorsQualityResult
} from '@/features/integrations/api/doorsQuality'
import type { Job } from '@/features/jobs/api/jobs'
import PageJobStatus from '@/features/jobs/components/PageJobStatus.vue'
import { usePageJob } from '@/features/jobs/composables/usePageJob'

const {
  job,
  active,
  cancelling,
  downloading,
  errorMessage,
  cancel,
  download,
  openJobCenter,
  setJob,
  refresh
} = usePageJob('doors_agent_job')
const modulePath = ref('')
const worker = ref<DoorsStatus | null>(null)
const statusLoading = ref(false)
const queueing = ref(false)
const lastError = ref('')
const result = ref<DoorsQualityResult | null>(null)
const resultLoading = ref(false)
const resultError = ref('')
const showDetails = ref(false)
let disposed = false
let resultRequest = 0
let pendingAttempt: { path: string; key: string } | null = null
const steps = [
  { progress: 10, label: 'Modülü aç ve attribute değerlerini oku' },
  { progress: 45, label: 'ATA chapter ve panel attribute’larını bul' },
  { progress: 55, label: 'Değerleri yorumla ve eksikleri belirle' },
  { progress: 80, label: 'Her chapter’ın tek panele bağlı olduğunu kontrol et' },
  { progress: 95, label: 'Bulguları ve çözüm önerilerini hazırla' }
]
const canQueue = computed(() =>
  Boolean(
    worker.value?.available &&
    modulePath.value.trim() &&
    !active.value &&
    !queueing.value &&
    !resultLoading.value
  )
)
const readinessMessage = computed(() => {
  if (!worker.value) return 'Windows DOORS worker durumu henüz doğrulanmadı.'
  if (!worker.value.configured) return 'Windows DOORS worker yapılandırılmamış.'
  if (!worker.value.available) return 'Windows DOORS worker şu anda erişilebilir değil.'
  return `${worker.value.active_workers} DOORS worker kullanılabilir.`
})
const resultTitle = computed(
  () =>
    ({
      passed: 'ATA–panel tutarlılık kontrolü geçti',
      review_required: 'İnceleme gerekiyor',
      incomplete: 'Kontrol tamamlanamadı'
    })[result.value?.outcome || 'incomplete']
)

onMounted(loadStatus)
onBeforeUnmount(() => {
  disposed = true
  resultRequest++
})
watch(
  () => [job.value?.id, job.value?.status],
  () => {
    resultRequest++
    result.value = null
    resultError.value = ''
    resultLoading.value = false
    showDetails.value = false
    if (job.value?.status === 'succeeded') void loadResult(job.value)
  }
)

async function loadStatus(): Promise<void> {
  statusLoading.value = true
  try {
    worker.value = await fetchDoorsStatus()
  } catch (error) {
    worker.value = null
    lastError.value = formatApiError(error)
  } finally {
    statusLoading.value = false
  }
}

async function queueCheck(): Promise<void> {
  if (!canQueue.value) return
  const path = modulePath.value.trim()
  if (pendingAttempt?.path !== path) pendingAttempt = { path, key: crypto.randomUUID() }
  queueing.value = true
  lastError.value = ''
  try {
    const queued = await enqueueDoorsQualityCheck(path, pendingAttempt.key)
    if (!disposed) setJob(queued)
    pendingAttempt = null
  } catch (error) {
    lastError.value = formatApiError(error)
  } finally {
    queueing.value = false
  }
}

async function loadResult(current: Job): Promise<void> {
  const request = ++resultRequest
  resultLoading.value = true
  resultError.value = ''
  try {
    const report = await fetchDoorsQualityResult(current)
    if (!disposed && request === resultRequest) result.value = report
  } catch (error) {
    if (!disposed && request === resultRequest) resultError.value = formatApiError(error)
  } finally {
    if (!disposed && request === resultRequest) resultLoading.value = false
  }
}

function stepLabel(start: number, next = 100): string {
  if (!job.value || job.value.progress < start) return 'Bekliyor'
  if (job.value.status === 'succeeded' || job.value.progress >= next) return 'Tamamlandı'
  if (job.value.status === 'failed' || job.value.status === 'reconciliation_required') return 'Hata'
  if (job.value.status === 'cancelled') return 'İptal edildi'
  return job.value.status === 'cancel_requested' ? 'İptal bekleniyor' : 'Çalışıyor'
}

function stepType(start: number, next?: number): 'default' | 'success' | 'error' | 'info' {
  const label = stepLabel(start, next)
  return label === 'Tamamlandı'
    ? 'success'
    : label === 'Hata'
      ? 'error'
      : label === 'Çalışıyor'
        ? 'info'
        : 'default'
}

function methodLabel(method: string): string {
  return (
    {
      exact: 'Doğrudan eşleşme',
      heuristic: 'Sezgisel eşleşme — doğrulayın',
      unresolved: 'Belirsiz'
    }[method] || method
  )
}
</script>
