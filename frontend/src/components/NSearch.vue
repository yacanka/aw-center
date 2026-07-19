<template>
  <n-dropdown
    :show="showDropdown"
    :options="options"
    placement="bottom-start"
    @select="handleSelect"
    @clickoutside="handleClickOutside"
    key-field="person_id"
    label-field="name"
    :style="{ width: '100%' }"
  >
    <template #default>
      <n-input
        ref="inputRef"
        :value="value"
        :status="currentStatus"
        :placeholder="placeholder"
        clearable
        @input="updateValue"
        @change="handleChange"
        @focus="isFocused = true"
        @blur="isFocused = false"
        :style="style"
      >
        <template #suffix>
          <n-select
            v-model:value="currentMod"
            :status="currentStatus"
            :options="modOptions"
            @update:value="handleModUpdate"
            style="width: 82px; transform: translateX(12px); color: 'red'"
          />
        </template>
      </n-input>
    </template>
  </n-dropdown>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, PropType } from 'vue'
import { findMostSimilarWord } from '@/utils/general'
import { IPerson } from '@/models/orgs'
import { useOrgsStore } from '@/stores/organizations'

type ModType = 'id' | 'name' | 'mail'

const props = defineProps({
  value: { type: String, default: '' },
  id: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  defaultMod: {
    type: String as PropType<ModType>,
    default: 'id',
    validator: (value: string) => {
      const result = ['id', 'name', 'mail'].includes(value)
      if (!result) console.warn("NSearch 'defaultMod' prop can be ['id' | 'name' | 'mail']")
      return result
    }
  },
  style: { type: Object, default: null },
  list: { type: Array<IPerson>, default: () => [] }
})

const emit = defineEmits(['update:value', 'change'])
const currentPerson = ref<IPerson | undefined>()
const currentMod = ref(props.defaultMod)
const inputRef = ref()
const showDropdown = ref(false)
const isFocused = ref(false)
const options = ref<IPerson[]>([])
const store = useOrgsStore()

const currentStatus = computed(() => {
  if (!isFocused.value) return 'default'
  if (props.value.length != 0 && options.value.length == 0) return 'warning'
  return 'success'
})

const modOptions = [
  { label: 'ID', value: 'id' },
  { label: 'Name', value: 'name' },
  { label: 'Mail', value: 'mail' }
]

let timeout: ReturnType<typeof setTimeout> | null = null
let requestOrder = 0

function updateValue(value: string) {
  if (timeout) clearTimeout(timeout)
  emit('update:value', value)

  if (value.trim().length == 0) {
    resetDropdown()
    return
  }

  timeout = setTimeout(() => searchPeople(value), 350)
}

function handleChange(value: string) {
  emit('change', value)
}

function handleClickOutside() {
  showDropdown.value = false
}

function handleModUpdate(val: ModType) {
  currentMod.value = val
  if (props.value) setText()
}

function setText() {
  const person = currentPerson.value
  if (currentMod.value == 'name') emit('update:value', person?.name)
  if (currentMod.value == 'id') emit('update:value', person?.person_id)
  if (currentMod.value == 'mail') emit('update:value', person?.email)
}

function handleSelect(key: string | number, option: IPerson) {
  currentPerson.value = option
  showDropdown.value = false
  inputRef.value.focus()
  setText()
  nextTick(() => inputRef.value.blur())
}

async function searchPeople(searchText: string) {
  const order = ++requestOrder
  try {
    const remotePeople = await store.searchPeople(searchText, 40)
    if (order != requestOrder) return

    options.value = chooseBestPeople(searchText, remotePeople, 10)
    showDropdown.value = options.value.length > 0
  } catch {
    if (order == requestOrder) resetDropdown()
  }
}

function resetDropdown() {
  options.value = []
  showDropdown.value = false
}

function chooseBestPeople(searchText: string, people: IPerson[], maxCount: number) {
  const result: IPerson[] = []
  for (const person of people) {
    if (!person.name || !isSimilarName(searchText, person.name)) continue
    result.push(person)
    if (result.length == maxCount) break
  }
  return result
}

function isSimilarName(searchText: string, personName: string) {
  const sentence = personName.substring(0, searchText.length + 3)
  const sentenceMatch = findMostSimilarWord(searchText, [sentence])
  if (sentenceMatch && sentenceMatch.distance < 4) return true

  const wordMatch = findMostSimilarWord(searchText, personName.split(' '))
  return !!wordMatch && wordMatch.distance < 2
}
</script>

<style scoped></style>
