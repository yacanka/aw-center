<template>
    <n-tabs v-model:value="activeListTab" type="card" size="small" addable @add="handleTabAdd" closable
        @close="handleTabClose" @update:value="handleTabUpdate">
        <template #prefix>
            <n-h3 style="margin: 0px;">Subtask Lists</n-h3>
        </template>
        <n-tab-pane v-for="(item, index) in subtaskLists" :name="index" :tab="item.title" :tab-props="tabPaneProps">
            <template #tab>
                <NInputWidth v-if="item.isTitleEdit" v-model:value="item.title" size="tiny" placeholder="Title"
                    @keydown.enter="onTitleEnter" @blur="onTitleEnter()" />
                <div v-else> {{ item.title }} </div>
            </template>
            <n-dynamic-input :value="item.list" :on-create="createListItem" :on-remove="removeListItem">
                <template #create-button-default>
                    Add subtask summary and assignee
                </template>
                <template #default="{ value }">
                    <n-grid cols=12 x-gap=12>
                        <n-grid-item span=8>
                            <n-input v-model:value="value.summary" placeholder="Summary" @change="activateSave()" />
                        </n-grid-item>
                        <n-grid-item span=4>
                            <n-search v-model:value="value.assignee" placeholder="Assignee" :list="store.getPeople"
                                @change="activateSave()" />
                        </n-grid-item>
                    </n-grid>
                </template>
            </n-dynamic-input>
        </n-tab-pane>
        <template #suffix>
            <n-button tertiary :type="saveButton.type" @click="saveAllList" :disabled="saveButton.type == 'default'">
                <template #icon>
                    <Save24Regular />
                </template>
                Save
            </n-button>
        </template>
    </n-tabs>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue';
import { useOrgsStore } from '@/stores/api';
import NSearch from '../NSearch.vue';
import NInputWidth from '../NInputWidth.vue';
import { Save24Regular, WindowShield16Filled } from '@vicons/fluent';
import { checkArrayEquals } from '@/utils/array';
import { ISubtaskItem, ISubtaskListItem } from '@/models/jira';



const store = useOrgsStore()

const activeListTab = ref()
const saveButton = ref({
    type: "default"
})
const props = defineProps({
    list: {
        type: Array<ISubtaskItem>,
        default: () => [],
        validator: (value) => {
            return Array.isArray(value)
        }
    },
})

const tabPaneProps = {
    ondblclick: () => {
        subtaskLists.value[activeListTab.value].isTitleEdit = true
    }
}

const emits = defineEmits(['update:list', 'change'])

let orijinalLists: ISubtaskListItem
const subtaskLists = ref<ISubtaskListItem[]>([])

function saveAllList() {
    window.$userStore.updatePreference({jira_list: subtaskLists.value})
    //localStorage.setItem("jira>subtask_lists", JSON.stringify(subtaskLists.value))
    saveButton.value.type = "default"
}

function activateSave() {
    saveButton.value.type = "warning"
}

function onTitleEnter() {
    subtaskLists.value[activeListTab.value].isTitleEdit = false

    activateSave()
}

function handleTabAdd() {
    subtaskLists.value.push({ title: "New List", list: [] as ISubtaskItem[] } as ISubtaskListItem)
    const lastListIndex = subtaskLists.value.length - 1
    activeListTab.value = lastListIndex
    localStorage.setItem("jira>activetab>sglist", lastListIndex.toString())
    emits("update:list", subtaskLists.value[lastListIndex].list)
    activateSave()
}

function handleTabClose(name: string | number) {
    subtaskLists.value.splice(name as number, 1)

    if (activeListTab.value == subtaskLists.value.length) {
        activeListTab.value = subtaskLists.value.length - 1
    }

    activateSave()
}

function handleTabUpdate(name: string | number) {
    localStorage.setItem("jira>activetab>sglist", name.toString())
    emits("update:list", subtaskLists.value[name as number].list)
}

function createListItem(index: number) {
    subtaskLists.value[activeListTab.value].list.push({} as ISubtaskItem)

    activateSave()
}

function removeListItem(index: number) {
    subtaskLists.value[activeListTab.value].list.splice(index, 1)

    activateSave()
}

onMounted(() => {
    subtaskLists.value = window.$userStore.getPreferences.jira_list || []
    //subtaskLists.value = JSON.parse(localStorage.getItem("jira>subtask_lists") || "[]");
    if (subtaskLists.value?.length == 0) {
        handleTabAdd()
    }

    activeListTab.value = parseInt(localStorage.getItem("jira>activetab>sglist") || "0");
    activeListTab.value = activeListTab.value < subtaskLists.value.length ? activeListTab.value : 0

    emits("update:list", subtaskLists.value[activeListTab.value].list)
})
</script>

<style scoped>
.auto-width-input {
    display: inline-block;
    position: relative;
}

.measure-span {
    visibility: hidden;
    white-space: pre;
    position: absolute;
    top: 0;
    left: 0;
    font-size: 14px;
    padding: 0;
    margin: 0;
    font-family: inherit;
}
</style>
