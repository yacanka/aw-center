<template>
  <n-modal v-model:show="popup.visible" preset="card" title="Change Password" :style="{ width: '700px' }"
    transform-origin="center">
    <n-form ref="formRef" :model="passwords" :rules="rules">
      <n-grid :x-gap="12" :cols="12">
        <n-form-item-gi span=12 path="current_password" label="Current Password">
          <n-input type="password" v-model:value="passwords.current_password" placeholder="Enter password"
            @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span=12 path="new_password" label="New Password">
          <n-input type="password" v-model:value="passwords.new_password" placeholder="Enter new password"
            @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span=12 path="confirm_password" label="Confirm Password">
          <n-input type="password" v-model:value="passwords.confirm_password" placeholder="Enter new password again"
            @keydown.enter.prevent />
        </n-form-item-gi>
      </n-grid>
      <n-flex justify="center" style="margin-top: 8px">
        <n-button @click="onClick" :disabled="popup.buttonDisabled">
          Save
        </n-button>
      </n-flex>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { validateForm } from '@/composables/forms'
import { FormRules } from 'naive-ui'

interface IChangePassword {
  current_password: string,
  new_password: string,
  confirm_password: string
}

const popup = ref({
  visible: false,
  buttonDisabled: false
})

const getFieldDefaults = () => {
  return {
    current_password: '',
    new_password: '',
    confirm_password: ''
  }
}
const passwords = ref<IChangePassword>(getFieldDefaults())
const formRef = ref()

const rules: FormRules = {
  current_password: [
    { required: true, trigger: "blur" },
  ],
  new_password: [
    { required: true, trigger: "blur" },
  ],
  confirm_password: [
    { required: true, trigger: "blur" },
    {
      validator: (rule, value) => {
        if (value != passwords.value.new_password) {
          return new Error("Passwords must match")
        }
        return true
      },
      trigger: ["blur"]
    }
  ],
}

async function onClick() {
  if (!await validateForm(formRef.value)) return
  try {
    window.$loadingBar.start()
    popup.value.buttonDisabled = true
    await window.$authStore.changePassword(passwords.value)
    popup.value.visible = false
    window.$loadingBar.finish()
  } catch (err) {
    window.$loadingBar.error()
  } finally {
    popup.value.buttonDisabled = false
  }
}


function openModal() {
  passwords.value = getFieldDefaults()
  popup.value.visible = true
}

defineExpose({
  openModal
})
</script>