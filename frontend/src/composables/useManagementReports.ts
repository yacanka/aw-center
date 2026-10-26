import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { ReportEnvelope, ReportPage, ReportProjectOption } from '@/models/managementReports'
import {
  captureReport,
  downloadReportPdf,
  fetchReportHistory,
  fetchReportOptions,
  fetchReportOverview,
  fetchSavedReport
} from '@/services/managementReports'
import {
  compatibleBaselines,
  createReportRequestGuard,
  normalizeReportScope
} from '@/services/managementReportHelpers'
import { formatApiError } from '@/services/apiError'

export function useManagementReports() {
  const options = ref<ReportProjectOption[]>([])
  const selected = ref<string[]>([])
  const envelope = ref<ReportEnvelope | null>(null)
  const history = ref<ReportPage>({ count: 0, next: null, previous: null, results: [] })
  const page = ref(1)
  const title = ref('')
  const note = ref('')
  const baseline = ref<string | null>(null)
  const loading = ref(false)
  const downloading = ref(false)
  const error = ref('')
  const initialized = ref(false)
  const guard = createReportRequestGuard()
  const historyGuard = createReportRequestGuard()
  const pdfGuard = createReportRequestGuard()
  const report = computed(() => envelope.value?.report || null)
  const baselines = computed(() =>
    report.value ? compatibleBaselines(history.value.results, report.value) : []
  )

  function scope() {
    return normalizeReportScope(
      selected.value,
      options.value.map((option) => option.slug)
    )
  }

  async function loadHistory(nextPage = 1) {
    const request = historyGuard.begin()
    try {
      const result = await fetchReportHistory(scope(), nextPage, request.signal)
      if (!request.isCurrent()) return
      history.value = result
      page.value = nextPage
    } catch (cause) {
      if (request.isCurrent()) error.value = formatApiError(cause)
    }
  }

  async function loadReport(mode: 'live' | 'save' | 'saved', id?: string) {
    const request = guard.begin()
    pdfGuard.cancel()
    downloading.value = false
    loading.value = true
    error.value = ''
    // Do not retain old report data while another selection is loading or denied.
    envelope.value = null
    try {
      let result: ReportEnvelope
      if (mode === 'saved' && id) {
        result = await fetchSavedReport(id, baseline.value || undefined, request.signal)
      } else if (mode === 'save') {
        result = await captureReport(scope(), title.value.trim(), note.value, request.signal)
      } else {
        result = await fetchReportOverview(scope(), request.signal)
      }
      if (!request.isCurrent()) return
      envelope.value = result
      if (mode === 'save') {
        title.value = ''
        note.value = ''
        await loadHistory()
      }
    } catch (cause) {
      if (request.isCurrent()) error.value = formatApiError(cause)
    } finally {
      if (request.isCurrent()) loading.value = false
    }
  }

  async function changeScope(value: string[]) {
    guard.cancel()
    historyGuard.cancel()
    pdfGuard.cancel()
    loading.value = false
    downloading.value = false
    selected.value = value
    envelope.value = null
    baseline.value = null
    error.value = ''
    history.value = { count: 0, next: null, previous: null, results: [] }
    page.value = 1
    if (value.length) await Promise.all([loadReport('live'), loadHistory()])
  }

  async function openSaved(id: string) {
    baseline.value = null
    await loadReport('saved', id)
  }

  async function compare(value: string | null) {
    const id = report.value?.id
    baseline.value = value
    if (id) await loadReport('saved', id)
  }

  async function download() {
    const id = report.value?.id
    if (!id) return
    const request = pdfGuard.begin()
    downloading.value = true
    error.value = ''
    try {
      const blob = await downloadReportPdf(id, baseline.value || undefined, request.signal)
      if (!request.isCurrent()) return
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `Management Report ${id}.pdf`
      anchor.click()
      // Give the browser a turn to acquire the download before releasing its URL.
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) {
      if (request.isCurrent()) error.value = formatApiError(cause)
    } finally {
      if (request.isCurrent()) downloading.value = false
    }
  }

  onMounted(async () => {
    const request = guard.begin()
    loading.value = true
    try {
      options.value = await fetchReportOptions(request.signal)
      if (!request.isCurrent()) return
      initialized.value = true
      await changeScope(options.value.map((option) => option.slug))
    } catch (cause) {
      if (request.isCurrent()) error.value = formatApiError(cause)
    } finally {
      if (request.isCurrent()) loading.value = false
    }
  })
  onBeforeUnmount(() => {
    guard.cancel()
    historyGuard.cancel()
    pdfGuard.cancel()
  })

  return {
    options,
    selected,
    envelope,
    report,
    history,
    page,
    title,
    note,
    baseline,
    baselines,
    loading,
    downloading,
    error,
    initialized,
    changeScope,
    loadHistory,
    openSaved,
    compare,
    refresh: () => {
      baseline.value = null
      return loadReport('live')
    },
    save: () => {
      baseline.value = null
      return loadReport('save')
    },
    download
  }
}
