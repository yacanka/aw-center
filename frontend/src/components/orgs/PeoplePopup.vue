<template>
  <n-modal v-model:show="showModal" preset="card" title="Person Information" :on-after-leave="onAfterLeave"
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
import { IPanel, IPerson, IProject } from '@/models/orgs'
import { FormRules, NModal } from 'naive-ui';
import { Edit24Regular } from '@vicons/fluent';
import { validateForm } from '@/composables/forms';

const rules = ref<FormRules>({
  name: [
    { required: true, trigger: "blur" }
  ],
  email: [
    { required: true, type: "email", trigger: "blur" }
  ],
  person_id: [
    { required: true, trigger: "blur" },
    { min: 6, max: 6, message: "Need 6 character", trigger: "blur" }
  ],
})

const formRef = ref()
const showModal = ref(false);
const person = ref<IPerson>({} as IPerson)
const popupMode = ref()
const projectOptions = ref([])
const panelOptions = ref([])

function openModal(value: IPerson, mode: string) {
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
  window.$orgsStore.createPerson(person.value)
}

async function updateDatabase() {
  if (!await validateForm(formRef.value)) return
  window.$orgsStore.updatePerson(person.value.id, person.value)
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
