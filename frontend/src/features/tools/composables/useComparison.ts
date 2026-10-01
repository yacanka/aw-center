import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { usePageJob } from '@/features/jobs/composables/usePageJob'
import { formatApiError } from '@/shared/api/apiError'
import {
  comparisonFamily,
  enqueueComparison,
  fetchComparisonPresets,
  fetchInspection,
  type ComparisonOptions,
  type ComparisonPreset,
  type ComparisonInspection,
  type ExcelSelection,
  type ComparisonInput
} from '@/features/tools/api/unifiedComparison'

/** Keep uploads, inspected snapshots and requests tied to one visible file pair. */
export function useComparison() {
  const monitor = usePageJob('comparison_job')
  const first = ref<File | null>(null)
  const second = ref<File | null>(null)
  const presets = ref<ComparisonPreset[]>([])
  const options = ref<ComparisonOptions>({
    preset: 'balanced',
    equal_ratio: 0.92,
    weak_equal_ratio: 0.7,
    output_type: 'word'
  })
  const inspection = ref<ComparisonInspection | null>(null)
  const inspectionId = ref<string | null>(null)
  const selection = ref<ExcelSelection>({})
  const queueing = ref(false)
  const loadingInspection = ref(false)
  const error = ref('')
  const inspectedSignature = ref('')
  let generation = 0
  let disposed = false
  let downloadOnCompletion: string | null = null
  let requestKey = ''
  let requestSignature = ''
  let inspectedJobId = ''

  const family = computed(() =>
    first.value ? comparisonFamily(first.value.name) : inspectionId.value ? 'excel' : null
  )
  const fileError = computed(() => {
    if (
      (first.value && !comparisonFamily(first.value.name)) ||
      (second.value && !comparisonFamily(second.value.name))
    ) {
      return 'Use DOCX/DOCM, XLSX/XLSM or PDF files.'
    }
    if (
      first.value &&
      second.value &&
      comparisonFamily(first.value.name) !== comparisonFamily(second.value.name)
    ) {
      return 'Both files must be the same type: Word, Excel or PDF.'
    }
    return ''
  })
  const validOptions = computed(
    () =>
      Number.isFinite(options.value.equal_ratio) &&
      Number.isFinite(options.value.weak_equal_ratio) &&
      options.value.weak_equal_ratio > 0 &&
      options.value.weak_equal_ratio <= options.value.equal_ratio &&
      options.value.equal_ratio <= 1
  )
  const busy = computed(() => queueing.value || monitor.active.value || loadingInspection.value)
  const signature = () =>
    JSON.stringify({
      selection: selection.value,
      preset: options.value.preset,
      equal: options.value.equal_ratio,
      weak: options.value.weak_equal_ratio
    })
  const dirty = computed(() =>
    Boolean(inspection.value && inspectedSignature.value !== signature())
  )
  const hasInput = computed(() =>
    Boolean((first.value && second.value && !fileError.value) || inspectionId.value)
  )
  const canInspect = computed(
    () =>
      !busy.value &&
      hasInput.value &&
      family.value === 'excel' &&
      validOptions.value &&
      presets.value.length > 0
  )
  const canCompare = computed(
    () =>
      !busy.value &&
      hasInput.value &&
      validOptions.value &&
      presets.value.length > 0 &&
      (family.value !== 'excel' ||
        Boolean(inspection.value && !dirty.value && !inspection.value.matching.requires_input))
  )

  function setFile(side: 'first' | 'second', file: File | null) {
    generation++
    if (side === 'first') first.value = file
    else second.value = file
    inspection.value = null
    inspectionId.value = null
    selection.value = {}
    inspectedSignature.value = ''
    inspectedJobId = ''
    monitor.reset()
    error.value = ''
    downloadOnCompletion = null
    requestSignature = ''
    options.value.output_type = family.value === 'excel' ? 'excel' : 'word'
  }

  function setPreset(preset: string) {
    options.value.preset = preset
    const chosen = presets.value.find((item) => item.id === preset)
    if (chosen) {
      options.value.equal_ratio = chosen.equal_ratio
      options.value.weak_equal_ratio = chosen.weak_equal_ratio
    }
  }

  function updateSelection(value: ExcelSelection) {
    selection.value = value
  }

  async function start(inspecting: boolean) {
    if (!(inspecting ? canInspect.value : canCompare.value)) return
    const input: ComparisonInput = inspectionId.value
      ? { inspectionId: inspectionId.value }
      : { files: [first.value!, second.value!] }
    const fingerprint = JSON.stringify({
      generation,
      inspecting,
      inspection: inspectionId.value,
      options: options.value,
      selection: selection.value
    })
    if (requestSignature !== fingerprint) {
      requestSignature = fingerprint
      requestKey = crypto.randomUUID()
    }
    const version = generation
    queueing.value = true
    error.value = ''
    try {
      const next = await enqueueComparison(
        inspecting,
        input,
        options.value,
        requestKey,
        inspecting ? selection.value : undefined
      )
      if (disposed || generation !== version) return
      downloadOnCompletion = inspecting ? null : next.id
      if (inspecting) inspectedJobId = ''
      monitor.setJob(next)
    } catch (caught) {
      if (!disposed && generation === version) error.value = formatApiError(caught)
    } finally {
      queueing.value = false
    }
  }

  async function loadInspection(id: string) {
    const version = generation
    inspectedJobId = id
    loadingInspection.value = true
    try {
      const data = await fetchInspection(id)
      if (disposed || generation !== version || monitor.job.value?.id !== id) return
      inspection.value = data
      inspectionId.value = id
      selection.value = structuredClone(data.selection)
      options.value = { ...data.options }
      inspectedSignature.value = signature()
    } catch (caught) {
      if (!disposed && generation === version) {
        error.value = formatApiError(caught)
        inspectedJobId = ''
      }
    } finally {
      loadingInspection.value = false
    }
  }

  watch(
    () => [monitor.job.value?.id, monitor.job.value?.status],
    async () => {
      const job = monitor.job.value
      if (job?.status !== 'succeeded') return
      if (job.kind === 'comparison.inspect' && inspectedJobId !== job.id)
        await loadInspection(job.id)
      if (job.kind === 'comparison.compare' && downloadOnCompletion === job.id) {
        downloadOnCompletion = null
        await monitor.download()
      }
    }
  )
  onMounted(async () => {
    try {
      presets.value = (await fetchComparisonPresets()).presets
    } catch (caught) {
      error.value = formatApiError(caught)
    }
  })
  onBeforeUnmount(() => {
    disposed = true
    generation++
  })

  return {
    ...monitor,
    first,
    second,
    family,
    fileError,
    options,
    presets,
    inspection,
    selection,
    queueing,
    loadingInspection,
    error,
    dirty,
    busy,
    canInspect,
    canCompare,
    validOptions,
    setFile,
    setPreset,
    updateSelection,
    inspect: () => start(true),
    compare: () => start(false),
    retryInspection: () => monitor.job.value && loadInspection(monitor.job.value.id)
  }
}
