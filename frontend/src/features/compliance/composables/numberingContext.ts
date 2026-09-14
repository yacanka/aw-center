import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { fetchNumberingFormat, type NumberingContextField } from '../api/compdocNumbering'
import { formatApiError } from '@/shared/api/apiError'

/** Load fields for the selected format, discarding stale replies after selection changes. */
export function useNumberingContext(
  project: Ref<string>,
  format: Ref<string | null>,
  enabled: Ref<boolean>,
  savedValues?: Ref<Record<string, string | number | boolean> | undefined>
) {
  const fields = ref<NumberingContextField[]>([])
  const values = ref<Record<string, string>>({})
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref('')
  let controller: AbortController | undefined
  const valid = computed(
    () =>
      loaded.value &&
      !loading.value &&
      !error.value &&
      fields.value.every((field) => {
        const value = values.value[field.key] || ''
        return (!field.required || Boolean(value.trim())) && [...value].length <= field.max_length
      })
  )
  const payload = computed(() =>
    Object.fromEntries(
      fields.value
        .filter((field) => values.value[field.key]?.trim())
        .map((field) => [field.key, values.value[field.key]])
    )
  )

  async function load() {
    controller?.abort()
    const current = new AbortController()
    controller = current
    fields.value = []
    values.value = {}
    error.value = ''
    loaded.value = false
    loading.value = false
    if (!enabled.value || !format.value) return
    loading.value = true
    try {
      const contract = await fetchNumberingFormat(project.value, format.value, current.signal)
      if (current.signal.aborted) return
      fields.value = contract.fields
      values.value = Object.fromEntries(
        contract.fields.map((field) => [
          field.key,
          savedValues?.value && Object.hasOwn(savedValues.value, field.key)
            ? String(savedValues.value[field.key])
            : ''
        ])
      )
      loaded.value = true
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : formatApiError(cause)
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  watch([project, format, enabled], () => void load(), { immediate: true })
  onBeforeUnmount(() => controller?.abort())
  return { fields, values, loading, loaded, error, valid, payload, load }
}
