<template>
  <n-modal v-model:show="showModal" preset="dialog" title="Document Information" centered width="500px">
    <n-form ref="formRef" :model="dcc" :rules="rules">
      <n-form-item path="issue" label="Issue">
        <n-input v-model:value="dcc.issue" disabled @keydown.enter.prevent />
      </n-form-item>
      <n-form-item path="dcc_path" label="DCC Path">
        <n-input v-model:value="dcc.dcc_path" @keydown.enter.prevent />
      </n-form-item>
      <n-form-item path="activeness" label="Activeness">
        <n-switch v-model:value="dcc.active" size="large">
          <template #checked>
            Active
          </template>
          <template #unchecked>
            Passive
          </template>
        </n-switch>
      </n-form-item>
    </n-form>
    <template #action>
      <n-button type="warning" ghost @click="updateDatabase">Update</n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { NModal, FormRules } from 'naive-ui';
import { IDcc } from '@/models/dcc';
import { validateForm } from '@/composables/forms';

const formRef = ref()
const rules = ref<FormRules>({
  issue: [
    {
      required: true,
    }
  ]
})

const showModal = ref(false);
const dcc = ref<IDcc>({} as IDcc)

function openModal(value: IDcc) {
  let dummy: IDcc = { ...value }
  dcc.value = dummy
  showModal.value = true;
}
function closeModal() {
  showModal.value = false;
}

async function updateDatabase() {
  if(!await validateForm(formRef.value)) return
  window.$dccStore.updateDcc(dcc.value.id, dcc.value)
  closeModal()
}

defineExpose({ openModal })

onMounted(() => {

});
</script>
