<template>
    <n-dropdown :show="showDropdown" :options="options" placement="bottom-start" @select="handleSelect"
        @clickoutside="handleClickOutside" key-field="person_id" label-field="name" :style="{ width: '100%' }">
        <template #default>
            <n-input ref="inputRef" :value="value" :status="currentStatus" :placeholder="placeholder" clerable
                @input="updateValue" @change="handleChange" @focus="isFocused = true" @blur="isFocused = false"
                :style="style">
                <template #suffix>
                    <n-select v-model:value="currentMod" :status="currentStatus" :options="modOptions"
                        @update:value="handleModUpdate" style="width: 82px; transform: translateX(12px); color:'red'" />
                </template>
            </n-input>
        </template>
    </n-dropdown>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, PropType, watchEffect } from 'vue'
import { findMostSimilarWord } from '@/utils/general'
import { IPerson } from '@/models/orgs'
import { useOrgsStore } from '@/stores/api'

type ModType = "id" | "name" | "mail"

const props = defineProps({
    value: {
        type: String,
        default: ''
    },
    id: {
        type: String,
        default: ''
    },
    placeholder: {
        type: String,
        default: ''
    },
    defaultMod: {
        type: String as PropType<ModType>,
        default: "id",
        validator: (value: string) => {
            const result = ["id", "name", "mail"].includes(value)
            if (!result) console.warn("NSearch 'defaultMod' prop can be ['id' | 'name' | 'mail']")
            return result
        }
    },
    style: {
        type: Object,
        default: null
    },
    list: {
        type: Array<IPerson>,
        default: () => [],
        validator: (value) => {
            return Array.isArray(value)
        }
    },
})

const currentPerson = ref<IPerson | undefined>({} as IPerson)
const currentMod = ref(props.defaultMod)
const inputRef = ref()
const showDropdown = ref(false)
const isFocused = ref(false)
const options = ref([] as IPerson[])
const emit = defineEmits(['update:value', 'change'])
const store = useOrgsStore()

const currentStatus = computed(() => isFocused.value ? (props.value.length != 0 && options.value.length == 0 ? 'warning' : 'success') : 'default')

const modOptions = [
    { label: "ID", value: "id" },
    { label: "Name", value: "name" },
    { label: "Mail", value: "mail" },
]

let timeout: any
const updateValue = (value: string) => {
    const setDropdownMenu = () => {
        const result = search(value, 2, 4, 10)
        options.value = result
        showDropdown.value = true
    }

    if (timeout) {
        clearTimeout(timeout)
    }

    if (value.length != 0) {
        timeout = setTimeout(setDropdownMenu, 500);
    } else {
        showDropdown.value = false
    }

    emit('update:value', value)
}

const handleChange = (value: string) => {
    emit('change', value)
}

onMounted(() => {
    currentPerson.value = props.list.find(person => person.person_id == props.value)
})

function handleClickOutside() {
    showDropdown.value = false
}

function handleModUpdate(val: ModType) {
    currentMod.value = val
    if (props.value) {
        setText()
    }
}

function setText() {
    if (currentMod.value == "name") {
        emit('update:value', currentPerson.value?.name)
    } else if (currentMod.value == "id") {
        emit('update:value', currentPerson.value?.person_id)
    } else if (currentMod.value == "mail") {
        emit('update:value', currentPerson.value?.email)
    }
}

function handleSelect(key: string | number, option: IPerson) {
    currentPerson.value = option
    showDropdown.value = false
    inputRef.value.focus()
    setText()
    nextTick(() => {
        inputRef.value.blur()
    })
}

function search(searchText: string, wordRatio: number, sentenceRatio: number, maxCount: number | null = null) {
    let list: IPerson[] = []
    for (let i = 0; i < props.list.length; i++) {
        const item = props.list[i];
        const parts = item.name.split(" ");
        let result: { distance: number, word: null } | null

        result = findMostSimilarWord(searchText, [item.name.substring(0, searchText.length + sentenceRatio - 1)])
        if (result && result.distance < sentenceRatio) {
            list.push(item)
        }

        result = findMostSimilarWord(searchText, parts)
        if (result && result.distance < wordRatio) {
            list.push(item)
        }

        list = [...new Set(list)]

        if (maxCount && list.length == maxCount) {
            break
        }
    }
    return list;
}
</script>

<style scoped></style>