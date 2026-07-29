<template>
  <n-modal
    v-model:show="showModal"
    preset="card"
    title="Responsible Information"
    :style="{ width: '40%', minWidth: '400px' }"
  >
    <template #header-extra>
      <n-button
        v-if="popupMode == 'view'"
        ghost
        type="warning"
        @click="setPopupMode('update')"
        size="small"
        style="margin: 10px"
      >
        <template #icon>
          <Edit24Regular />
        </template>
      </n-button>
    </template>

    <n-form ref="formRef" :model="person" :rules="rules">
      <n-grid :x-gap="12" :cols="12">
        <n-form-item-gi span="4" path="project" label="Project">
          <n-select
            v-model:value="person.project"
            :options="projectOptions"
            placeholder="Select Project"
            disabled
          />
        </n-form-item-gi>
        <n-form-item-gi span="6" path="panel" label="Panel">
          <n-select
            v-model:value="person.panel"
            :options="panelOptions"
            placeholder="Select Panel"
          />
        </n-form-item-gi>
        <n-form-item-gi span="2" path="title" label="Title">
          <n-select
            v-model:value="person.title"
            :options="titleOptions"
            placeholder="Select Title"
          />
        </n-form-item-gi>
        <n-form-item-gi span="12" path="person_id" label="Person">
          <n-search
            v-model:value="personSearchText"
            default-mod="name"
            placeholder="Search People by ID, name, or email"
            @select="selectDirectoryPerson"
          />
        </n-form-item-gi>
      </n-grid>
    </n-form>

    <template #action>
      <n-flex justify="center">
        <n-button v-if="popupMode == 'new'" type="success" @click="addDatabase">Add</n-button>
        <n-button v-else-if="popupMode == 'update'" type="warning" @click="updateDatabase"
          >Update</n-button
        >
      </n-flex>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  IPanel,
  IProject,
  IResponsible,
  type IPerson,
  type OrganizationOption
} from '@/models/orgs'
import { FormRules, NModal } from 'naive-ui'
import { Edit24Regular } from '@vicons/fluent'
import { validateForm } from '@/composables/forms'
import NSearch from '@/components/NSearch.vue'

const requiredRule = { required: true, trigger: 'blur' } as const
const rules = ref<FormRules>({
  panel: [requiredRule],
  title: [requiredRule],
  person_id: [requiredRule]
})

const formRef = ref()
const showModal = ref(false)
const person = ref<IResponsible>({} as IResponsible)
const personSearchText = ref('')
const popupMode = ref()
const projectOptions = ref<OrganizationOption[]>([])
const panelOptions = ref<OrganizationOption[]>([])

const titleOptions = [
  { value: 'AS', label: 'AS' },
  { value: 'CVE', label: 'CVE' },
  { value: 'IPT', label: 'IPT' },
  { value: 'SSB', label: 'SSB' },
  { value: 'Air Force', label: 'Air Force' },
  { value: 'PSK', label: 'PSK' },
  { value: 'PCE', label: 'PCE' }
]

function openModal(value: IResponsible, mode: string) {
  popupMode.value = mode
  const dummy = JSON.parse(JSON.stringify(value))
  person.value = dummy
  personSearchText.value = mode == 'new' ? '' : dummy.name
  showModal.value = true
  projectOptions.value = window.$orgsStore.getProjects.map((project: IProject) => {
    return { label: project.display_name, value: project.slug }
  })
  panelOptions.value = window.$orgsStore.getPanels.map((panel: IPanel) => {
    return { label: `${panel.ata} (${panel.name})`, value: panel.ata }
  })
}

function selectDirectoryPerson(selectedPerson: IPerson | null): void {
  person.value.person_id = selectedPerson?.person_id ?? ''
}

function closeModal() {
  showModal.value = false
}

async function addDatabase() {
  if (!(await validateForm(formRef.value))) return
  try {
    await window.$orgsStore.createResponsible(person.value)
    closeModal()
  } catch (err) {
    console.error(err)
  }
}

async function updateDatabase() {
  if (!(await validateForm(formRef.value))) return
  if (person.value.id === undefined) {
    throw new Error('Cannot update a responsible person without an ID.')
  }
  try {
    await window.$orgsStore.updateResponsible(person.value.id, person.value)
    closeModal()
  } catch (err) {
    console.error(err)
  }
}

function setPopupMode(mode: string) {
  popupMode.value = mode
}

defineExpose({ openModal })
</script>
