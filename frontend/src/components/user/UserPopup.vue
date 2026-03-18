<template>
  <n-modal v-model:show="showModal" preset="dialog" title="User Information" centered
    :style="{ width: '60%', minWidth: '600px' }">
    <n-form ref="formRef" :model="user" :rules="rules">
      <n-grid :x-gap="12" :cols="12">
        <n-form-item-gi span=2 path="username" label="Username">
          <n-input v-model:value="user.username" disbaled @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span=4 path="email" label="Email">
          <n-input v-model:value="user.email" disbaled @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span=3 path="first_name" label="First Name">
          <n-input v-model:value="user.first_name" @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span=3 path="last_name" label="Last Name">
          <n-input v-model:value="user.last_name" @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span=12 path="permissions" label="Permissions">
          <n-transfer v-model:value="user.user_permissions" :options="transferOptions"
            source-title="Available Permissions" target-title="Possessed Permissions" source-filterable
            @update:value="handleTransferChange" />
        </n-form-item-gi>
      </n-grid>
    </n-form>

    <template #action>
      <n-button type="warning" @click="updateDatabase">Update</n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { IUser } from '@/models/auth'
import { useAuthStore } from '@/stores/api'
import { FormRules, NModal } from 'naive-ui';
import { validateForm } from '@/composables/forms';

const rules = ref<FormRules>({
  username: [
    {
      required: true,
      trigger: "blur",
    }
  ],
  email: [
    {
      required: true,
      trigger: "blur",
    }
  ],
  first_name: [
    {
      required: true,
      trigger: "blur",
    }
  ],
  last_name: [
    {
      required: true,
      trigger: "blur",
    }
  ],
})

const transferValues = ref<number[]>([])

const formRef = ref()
const showModal = ref(false);
const user = ref<IUser>({} as IUser)
const store = useAuthStore()
const transferOptions = ref<{ label: string, value: number }[]>([])

function openModal(value: IUser) {
  let dummy: IUser = { ...value }
  user.value = dummy
  user.value.permissions.sort()
  transferValues.value = user.value.permissions.map(permission => permission.id)
  transferOptions.value = store.getPermissions.map(permission => ({ label: permission.content_type.app_label.toUpperCase() + " | " + permission.codename, value: permission.id }));

  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
}

async function updateDatabase() {
  if (!await validateForm(formRef.value)) return
  window.$authStore.updateUser(user.value.id, user.value)
  closeModal()
}

function handleTransferChange(value: any) {
  transferValues.value.sort()
}

defineExpose({ openModal })

onMounted(() => {

});
</script>
