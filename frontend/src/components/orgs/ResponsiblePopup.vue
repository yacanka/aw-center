<template>
  <n-modal v-model:show="showModal" preset="card" title="Responsible Information" :on-after-leave="onAfterLeave"
    :style="{ width: '40%', minWidth: '400px' }">
    <template #header-extra>
      <n-button v-if="popupMode == 'view'" ghost type="warning" @click="setPopupMode('update')" size="small"
        style="margin: 10px">
        <template #icon>
          <Edit24Regular />
        </template>
      </n-button>
    </template>

    <n-form ref="formRef" :model="person" :rules="rules">
      <n-grid :x-gap="12" :cols="12">
        <n-form-item-gi span=4 path="project" label="Project">
          <n-select v-model:value="person.project" :options="projectOptions" placeholder="Select Project" disabled />
        </n-form-item-gi>
        <n-form-item-gi span=6 path="panel" label="Panel">
          <n-select v-model:value="person.panel" :options="panelOptions" placeholder="Select Panel" />
        </n-form-item-gi>
        <n-form-item-gi span=2 path="title" label="Title">
          <n-select v-model:value="person.title" :options="titleOptions" placeholder="Select Title" />
        </n-form-item-gi>
        <n-form-item-gi span=2 path="person_id" label="ID">
          <n-input v-model:value="person.person_id" @keydown.enter.prevent :readonly="popupMode == 'view'" />
        </n-form-item-gi>
        <n-form-item-gi span=4 path="name" label="Name">
          <n-input v-model:value="person.name" @keydown.enter.prevent :readonly="popupMode == 'view'" />
        </n-form-item-gi>
        <n-form-item-gi span=6 path="email" label="Email">
          <n-input type="email" v-model:value="person.email" @keydown.enter.prevent :readonly="popupMode == 'view'" />
        </n-form-item-gi>
      </n-grid>
    </n-form>

    <template #action>
      <n-flex justify="center">
        <n-button v-if="popupMode == 'new'" type="success" @click="addDatabase">Add</n-button>
        <n-button v-else-if="popupMode == 'update'" type="warning" @click="updateDatabase">Update</n-button>
      </n-flex>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { IPanel, IProject, IResponsible } from '@/models/orgs'
import { FormRules, NModal } from 'naive-ui';
import { Edit24Regular } from '@vicons/fluent';
import { validateForm } from '@/composables/forms';

const rules = ref<FormRules>({
  panel: [
    {
      required: true,
      trigger: "blur"
    }
  ],
  name: [
    {
      required: true,
      trigger: "blur"
    }
  ],
  email: [
    {
      required: true,
      trigger: "blur"
    }
  ],
  title: [
    {
      required: true,
      trigger: "blur"
    }
  ],
  person_id: [
    {
      required: true,
      trigger: "blur"
    }
  ],
})

const formRef = ref()
const showModal = ref(false);
const person = ref<IResponsible>({} as IResponsible)
const popupMode = ref()
const projectOptions = ref([])
const panelOptions = ref([])

const titleOptions = [
  { value: "AS", label: "AS" },
  { value: "CVE", label: "CVE" },
  { value: "IPT", label: "IPT" },
  { value: "SSB", label: "SSB" },
  { value: "Air Force", label: "Air Force" },
  { value: "PSK", label: "PSK" },
  { value: "PCE", label: "PCE" },
]

function openModal(value: IResponsible, mode: string) {
  popupMode.value = mode
  const dummy = JSON.parse(JSON.stringify(value))
  person.value = dummy
  showModal.value = true;
  projectOptions.value = window.$orgsStore.getProjects.map((project: IProject) => {
    return { label: project.name, value: project.name }
  })
  panelOptions.value = window.$orgsStore.getPanels.map((panel: IPanel) => {
    return { label: `${panel.ata} (${panel.name})`, value: panel.ata }
  })
}

function closeModal() {
  showModal.value = false;
}

async function addDatabase() {
  if (!await validateForm(formRef.value)) return
  window.$orgsStore.createResponsible(person.value)
}

async function updateDatabase() {
  if (!await validateForm(formRef.value)) return
  window.$orgsStore.updateResponsible(person.value.id, person.value)
  closeModal()
}

function setPopupMode(mode: string) {
  popupMode.value = mode
}

function handleItemHeaderClick(value: any) {

}

function onAfterLeave() {

}

defineExpose({ openModal })

onMounted(() => {

});
</script>
