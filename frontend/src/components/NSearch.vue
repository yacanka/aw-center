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
import { usePeopleSearch, type PeopleSearchState } from '@/composables/usePeopleSearch'

type SearchMode = 'id' | 'name' | 'mail'
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
  search: [query: string]
}>()

const inputRef = ref<InputInst | null>(null)
const currentPerson = ref<IPerson>()
const currentMode = ref<SearchMode>(props.defaultMod)
const isFocused = ref(false)
const search = usePeopleSearch((query) => emit('search', query))
let blurTimer: ReturnType<typeof setTimeout> | null = null

const modeOptions = [
  { label: 'ID', value: 'id' },
  { label: 'Name', value: 'name' },
  { label: 'Mail', value: 'mail' }
]

const dropdownOptions = computed<PersonOption[]>(() => {
  const options = search.people.value.map(toPersonOption)
  const stateOption = toStateOption(search.state.value, options.length > 0)
  if (stateOption) options.push(stateOption)
  if (search.hasMore.value && !['loading-more', 'error'].includes(search.state.value)) {
    options.push(loadMoreOption())
  }
  return options
})
const showDropdown = computed(
  () => isFocused.value && props.value.trim().length > 0 && dropdownOptions.value.length > 0
)
const currentStatus = computed(() => {
  if (!isFocused.value) return 'default'
  if (search.state.value == 'error') return 'error'
  if (search.state.value == 'empty') return 'warning'
  if (search.people.value.length) return 'success'
  return 'default'
})

function updateValue(value: string): void {
  emit('update:value', value)
  currentPerson.value = undefined
  search.schedule(value)
}

function handleSelect(key: string | number, option: PersonOption): void {
  if (key == 'load-more') return keepDropdownOpen(search.loadMore)
  if (key == 'retry-search') return keepDropdownOpen(search.retry)
  if (!option.person) return
  clearBlurTimer()
  currentPerson.value = option.person
  isFocused.value = false
  setSelectedPersonText()
  nextTick(() => inputRef.value?.blur())
}

function setSelectedPersonText(): void {
  const person = currentPerson.value
  if (!person) return
  const values = { id: person.person_id, name: person.name, mail: person.email }
  const selectedValue = values[currentMode.value]
  emit('update:value', selectedValue)
  emit('search', selectedValue)
}

function handleFocus(): void {
  isFocused.value = true
  if (props.value.trim().length >= 2 && search.state.value == 'idle') {
    search.schedule(props.value, 0)
  }
}

function handleBlur(): void {
  clearBlurTimer()
  blurTimer = window.setTimeout(() => (isFocused.value = false), 120)
}

function keepDropdownOpen(action: () => void): void {
  clearBlurTimer()
  isFocused.value = true
  action()
  nextTick(() => inputRef.value?.focus())
}

function clearBlurTimer(): void {
  if (blurTimer) clearTimeout(blurTimer)
  blurTimer = null
}

function toPersonOption(person: IPerson): PersonOption {
  return {
    key: person.id ?? person.person_id,
    label: `${person.name} — ${person.person_id} · ${person.email}`,
    person
  }
}

function stateMessage(state: PeopleSearchState): string {
  if (state == 'short') return 'Type at least 2 characters.'
  if (state == 'loading') return 'Searching people…'
  if (state == 'loading-more') return 'Loading more people…'
  if (state == 'empty') return 'No matching person found.'
  if (state == 'error') return 'People search failed. Please try again.'
  return ''
}

function toStateOption(state: PeopleSearchState, hasPeople: boolean): PersonOption | undefined {
  if (state == 'error') return { key: 'retry-search', label: stateMessage(state) }
  const message = stateMessage(state)
  if (!message || (hasPeople && state != 'loading-more')) return undefined
  return { key: `state-${state}`, label: message, disabled: true }
}

function loadMoreOption(): PersonOption {
  const remaining = Math.max(search.total.value - search.people.value.length, 0)
  return { key: 'load-more', label: `Show more results (${remaining} remaining)` }
}

onBeforeUnmount(clearBlurTimer)
</script>
