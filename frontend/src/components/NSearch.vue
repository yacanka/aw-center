<template>
  <n-dropdown
    :show="showDropdown"
    :options="dropdownOptions"
    placement="bottom-start"
    :style="{ width: '100%' }"
    @select="handleSelect"
    @clickoutside="isFocused = false"
  >
    <n-input
      ref="inputRef"
      :value="value"
      :status="currentStatus"
      :placeholder="placeholder"
      :style="style"
      clearable
      @input="updateValue"
      @change="emit('change', $event)"
      @focus="handleFocus"
      @blur="handleBlur"
    >
      <template #suffix>
        <n-select
          v-model:value="currentMode"
          :status="currentStatus"
          :options="modeOptions"
          style="width: 82px; transform: translateX(12px)"
          @update:value="setSelectedPersonText"
        />
      </template>
    </n-input>
  </n-dropdown>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, type CSSProperties } from 'vue'
import type { InputInst } from 'naive-ui'
import type { IPerson } from '@/models/orgs'
import { useOrgsStore } from '@/stores/organizations'

type SearchMode = 'id' | 'name' | 'mail'
type SearchState = 'idle' | 'short' | 'loading' | 'ready' | 'empty' | 'error'
type PersonOption = {
  key: string | number
  label: string
  disabled?: boolean
  person?: IPerson
}

const props = withDefaults(
  defineProps<{
    value?: string
    placeholder?: string
    defaultMod?: SearchMode
    style?: CSSProperties
  }>(),
  { value: '', placeholder: '', defaultMod: 'id', style: undefined }
)

const emit = defineEmits<{
  'update:value': [value: string]
  change: [value: string]
}>()

const store = useOrgsStore()
const inputRef = ref<InputInst | null>(null)
const currentPerson = ref<IPerson>()
const currentMode = ref<SearchMode>(props.defaultMod)
const peopleOptions = ref<PersonOption[]>([])
const searchState = ref<SearchState>('idle')
const isFocused = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let activeController: AbortController | null = null
let requestOrder = 0

const modeOptions = [
  { label: 'ID', value: 'id' },
  { label: 'Name', value: 'name' },
  { label: 'Mail', value: 'mail' }
]

const dropdownOptions = computed<PersonOption[]>(() => {
  const message = stateMessage(searchState.value)
  return message
    ? [{ key: `state-${searchState.value}`, label: message, disabled: true }]
    : peopleOptions.value
})
const showDropdown = computed(
  () => isFocused.value && props.value.trim().length > 0 && dropdownOptions.value.length > 0
)
const currentStatus = computed(() => {
  if (!isFocused.value) return 'default'
  if (searchState.value == 'error') return 'error'
  if (searchState.value == 'empty') return 'warning'
  if (searchState.value == 'ready') return 'success'
  return 'default'
})

function updateValue(value: string): void {
  emit('update:value', value)
  currentPerson.value = undefined
  scheduleSearch(value)
}

function scheduleSearch(value: string, delay = 300): void {
  cancelPendingSearch()
  peopleOptions.value = []
  if (!value.trim()) return setState('idle')
  if (value.trim().length < 2) return setState('short')
  searchState.value = 'loading'
  debounceTimer = setTimeout(() => searchPeople(value), delay)
}

async function searchPeople(value: string): Promise<void> {
  const order = ++requestOrder
  const controller = new AbortController()
  activeController = controller
  try {
    const people = await store.searchPeople(value, 10, controller.signal)
    if (order != requestOrder) return
    peopleOptions.value = people.map(toPersonOption)
    searchState.value = people.length ? 'ready' : 'empty'
  } catch {
    if (order == requestOrder) searchState.value = 'error'
  } finally {
    if (activeController == controller) activeController = null
  }
}

function handleSelect(_key: string | number, option: PersonOption): void {
  if (!option.person) return
  currentPerson.value = option.person
  isFocused.value = false
  setSelectedPersonText()
  nextTick(() => inputRef.value?.blur())
}

function setSelectedPersonText(): void {
  const person = currentPerson.value
  if (!person) return
  const values = { id: person.person_id, name: person.name, mail: person.email }
  emit('update:value', values[currentMode.value])
}

function handleFocus(): void {
  isFocused.value = true
  if (props.value.trim().length >= 2 && searchState.value == 'idle') scheduleSearch(props.value, 0)
}

function handleBlur(): void {
  window.setTimeout(() => (isFocused.value = false), 120)
}

function cancelPendingSearch(): void {
  requestOrder += 1
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = null
  activeController?.abort()
  activeController = null
}

function setState(state: SearchState): void {
  searchState.value = state
}

function toPersonOption(person: IPerson): PersonOption {
  return {
    key: person.id ?? person.person_id,
    label: `${person.name} — ${person.person_id} · ${person.email}`,
    person
  }
}

function stateMessage(state: SearchState): string {
  if (state == 'short') return 'Type at least 2 characters.'
  if (state == 'loading') return 'Searching people…'
  if (state == 'empty') return 'No matching person found.'
  if (state == 'error') return 'People search failed. Please try again.'
  return ''
}

onBeforeUnmount(cancelPendingSearch)
</script>
