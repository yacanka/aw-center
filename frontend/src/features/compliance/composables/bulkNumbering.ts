import { computed, onBeforeUnmount, ref, type Ref } from 'vue'
import {
  createCoverPageAllocation,
  fetchCoverPageAllocation,
  fetchExistingCoverPageAllocation,
  fetchNumberingOptions,
  resumeCoverPageAllocation,
  type CoverPageAllocation
} from '../api/compdocNumbering'
import { buildCompdocUpdatePayload } from '../api/compdocPayload'
import type { ICompDoc } from '../models/compdocs'
import { documentNumberingContext, useNumberingContext } from './numberingContext'
import { formatApiError } from '@/shared/api/apiError'

interface NumberingRow {
  document: ICompDoc
  operationId: string
  selected: boolean
  allocation: CoverPageAllocation | null
  error: string
}

function active(allocation: CoverPageAllocation | null): boolean {
  return ['queued', 'running', 'cancel_requested'].includes(allocation?.job?.status || '')
}

/** Each row retains its own durable allocation identity, including after uncertain responses. */
export function useBulkNumbering(
  project: string,
  canEdit: Ref<boolean>,
  acceptDocument: (document: unknown) => void,
  visibleDocuments: Ref<ICompDoc[]>
) {
  const visible = ref(false)
  const loading = ref(false)
  const submitting = ref(false)
  const refreshing = ref(false)
  const started = ref(false)
  const available = ref(false)
  const formats = ref<string[]>([])
  const format = ref('')
  const submittedContext = ref<Record<string, string>>()
  const rows = ref<NumberingRow[]>([])
  const context = useNumberingContext(
    ref(project),
    format,
    computed(() => visible.value && available.value),
    submittedContext,
    computed(() => rows.value.filter((row) => row.selected).map((row) => row.document))
  )
  let pageIds = ''
  const currentPageIds = () =>
    visibleDocuments.value
      .map((doc) => doc.id)
      .sort()
      .join(',')
  const error = ref('')
  let disposed = false
  let timer: ReturnType<typeof setTimeout> | undefined
  const selected = computed(() => rows.value.filter((row) => row.selected))
  const completed = computed(
    () => selected.value.filter((row) => row.allocation?.status === 'completed').length
  )
  const actionable = computed(() =>
    selected.value.filter(
      (row) => row.allocation?.status !== 'completed' && (!active(row.allocation) || row.error)
    )
  )
  const canSubmit = computed(
    () =>
      canEdit.value &&
      available.value &&
      formats.value.includes(format.value) &&
      (started.value || context.valid.value) &&
      !loading.value &&
      !submitting.value &&
      !refreshing.value &&
      actionable.value.length > 0
  )

  async function open() {
    visible.value = true
    if (pageIds !== currentPageIds()) started.value = false
    if (started.value) await refresh()
    else await load()
  }

  async function load() {
    if (loading.value || started.value) return
    loading.value = true
    error.value = ''
    rows.value = []
    available.value = false
    submittedContext.value = undefined
    pageIds = currentPageIds()
    const documents: ICompDoc[] = JSON.parse(
      JSON.stringify(
        visibleDocuments.value.filter(
          (document) => document.id && !document.is_archived && !document.cover_page_no.trim()
        )
      )
    )
    try {
      const options = await fetchNumberingOptions(project)
      if (disposed) return
      available.value = options.available
      formats.value = options.formats
      format.value = options.formats.length === 1 ? options.formats[0] : ''
      rows.value = documents.map((document) => ({
        document,
        operationId: crypto.randomUUID(),
        selected: true,
        allocation: null,
        error: ''
      }))
    } catch (cause) {
      if (!disposed) error.value = formatApiError(cause)
    } finally {
      loading.value = false
    }
  }

  async function chooseMore() {
    if (submitting.value || refreshing.value || completed.value !== selected.value.length) return
    started.value = false
    await load()
  }

  function accept(row: NumberingRow, allocation: CoverPageAllocation) {
    if (disposed) return
    const wasCompleted = row.allocation?.status === 'completed'
    row.allocation = allocation
    row.error = ''
    if (!wasCompleted && allocation.status === 'completed' && allocation.document) {
      acceptDocument(allocation.document)
    }
  }

  async function submitRow(row: NumberingRow) {
    try {
      if (!visibleDocuments.value.some((document) => document.id === row.document.id)) {
        row.error = 'This document is no longer on the visible table page.'
        return
      }
      const existing = row.allocation
        ? await fetchCoverPageAllocation(project, row.allocation.id)
        : await fetchExistingCoverPageAllocation(project, row.document.id!)
      if (disposed || !canEdit.value) return
      if (existing) {
        accept(row, existing)
        if (existing.status !== 'completed' && !active(existing)) {
          accept(row, await resumeCoverPageAllocation(project, existing))
        }
        return
      }
      accept(
        row,
        await createCoverPageAllocation(
          project,
          row.operationId,
          buildCompdocUpdatePayload(row.document),
          row.document.id,
          format.value,
          documentNumberingContext(submittedContext.value || {}, row.document)
        )
      )
    } catch (cause) {
      if (!disposed) row.error = formatApiError(cause)
    }
  }

  async function submit() {
    if (!canSubmit.value) return
    clearTimeout(timer)
    submitting.value = true
    if (!started.value) submittedContext.value = { ...context.payload.value }
    started.value = true
    const pending = [...actionable.value]
    for (const row of pending) {
      if (disposed || !canEdit.value) break
      await submitRow(row)
    }
    submitting.value = false
    schedule()
  }

  function schedule() {
    clearTimeout(timer)
    if (
      !disposed &&
      visible.value &&
      rows.value.some((row) => active(row.allocation) && !row.error)
    ) {
      timer = setTimeout(() => void refresh(), 2000)
    }
  }

  async function refresh() {
    if (refreshing.value || submitting.value || disposed) return
    clearTimeout(timer)
    refreshing.value = true
    for (const row of rows.value) {
      if (disposed || !visible.value) break
      if (!row.allocation || row.allocation.status === 'completed') continue
      try {
        accept(row, await fetchCoverPageAllocation(project, row.allocation.id))
      } catch (cause) {
        if (!disposed) row.error = formatApiError(cause)
      }
    }
    refreshing.value = false
    schedule()
  }

  function close() {
    if (submitting.value) return
    visible.value = false
    clearTimeout(timer)
  }

  function status(row: NumberingRow): string {
    if (row.error) return row.error
    const allocation = row.allocation
    if (!allocation) return row.selected ? 'Ready' : 'Not selected'
    if (allocation.status === 'completed') return allocation.number
    if (active(allocation)) return allocation.job?.message || 'Queued'
    return allocation.error_detail || allocation.job?.message || 'Needs attention'
  }

  onBeforeUnmount(() => {
    disposed = true
    clearTimeout(timer)
  })
  return {
    context,
    visible,
    loading,
    submitting,
    refreshing,
    started,
    available,
    formats,
    format,
    error,
    rows,
    selected,
    completed,
    canSubmit,
    actionable,
    open,
    load,
    chooseMore,
    submit,
    refresh,
    close,
    status
  }
}
