<template>
  <n-card v-if="userId && userToken" title="Set new password" size="large">
    <n-form
      ref="confirmationForm"
      :model="passwordRequest"
      size="large"
      :rules="confirmationRules"
      label-placement="top"
    >
      <n-grid :x-gap="12" :cols="6">
        <n-form-item-gi span="6" label="Password" path="password">
          <n-input
            v-model:value="passwordRequest.password"
            type="password"
            placeholder="Enter your new password"
            show-password-on="mousedown"
          />
        </n-form-item-gi>
        <n-form-item-gi span="6" label="Confirm Password" path="passwordConfirm">
          <n-input
            v-model:value="passwordRequest.passwordConfirm"
            type="password"
            placeholder="Enter your new password again"
            show-password-on="mousedown"
          />
        </n-form-item-gi>
        <n-form-item-gi span="6">
          <n-button type="primary" attr-type="submit" @click="updatePassword">Update</n-button>
        </n-form-item-gi>
      </n-grid>
    </n-form>
  </n-card>
  <n-modal
    v-model:show="requestState.visible"
    preset="card"
    title="Reset Password"
    class="app-modal"
    :mask-closable="true"
  >
    <n-form
      ref="requestForm"
      :model="requestState"
      size="large"
      :rules="requestRules"
      label-placement="top"
    >
      <n-grid responsive="self" item-responsive :x-gap="12" :cols="12">
        <n-form-item-gi span="0:12 480:10" label="Email" path="email">
          <n-input
            v-model:value="requestState.email"
            type="email"
            placeholder="Enter your email"
            :disabled="requestPending"
          />
        </n-form-item-gi>
        <n-form-item-gi span="0:12 480:2">
          <n-button
            style="width: 100%"
            type="primary"
            attr-type="submit"
            :disabled="requestPending"
            @click="sendResetRequest"
          >
            Send
          </n-button>
        </n-form-item-gi>
      </n-grid>
      <n-tag class="reset-status" :type="requestState.status">
        {{ requestState.footerText }}
      </n-tag>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { FormInst, FormRules } from 'naive-ui'
import { useRouter } from 'vue-router'
import { validateForm } from '@/shared/composables/forms'
import { formatApiError } from '@/shared/api/apiError'
import { useSessionStore } from '@/features/session/stores/session'

type Status = 'error' | 'default' | 'success' | 'warning'
const props = defineProps<{ userId: string; userToken: string }>()
const router = useRouter()
const userStore = useSessionStore()
const requestForm = ref<FormInst | null>(null)
const confirmationForm = ref<FormInst | null>(null)
const requestState = ref({ visible: false, status: 'default' as Status, footerText: '', email: '' })
const passwordRequest = ref({ password: '', passwordConfirm: '' })
const requestPending = computed(() => requestState.value.status === 'warning')
const requestRules: FormRules = {
  email: [
    { required: true, message: 'Email required', trigger: 'blur' },
    { type: 'email', message: 'Enter a valid email address', trigger: 'blur' }
  ]
}
const confirmationRules: FormRules = {
  password: [{ required: true, message: 'Password required', trigger: 'blur' }],
  passwordConfirm: [
    { required: true, message: 'Password confirmation required', trigger: 'blur' },
    { validator: validateConfirmation, trigger: ['blur', 'input'] }
  ]
}

/** Open and reset the password recovery request dialog. */
function openRequestModal(): void {
  requestState.value = {
    visible: true,
    status: 'default',
    footerText: 'A password reset link will be sent to your email.',
    email: ''
  }
}

async function sendResetRequest(): Promise<void> {
  if (!(await validateForm(requestForm.value))) return
  setRequestStatus('warning', 'Sending...')
  try {
    await userStore.resetPasswordRequest({ email: requestState.value.email })
    setRequestStatus('success', 'A password reset link has been sent to your email.')
    window.$message.success('Check your inbox for the password reset link.')
  } catch (error) {
    setRequestStatus('error', formatApiError(error))
  }
}

async function updatePassword(): Promise<void> {
  if (!(await validateForm(confirmationForm.value))) return
  try {
    await userStore.resetPasswordConfirm(buildConfirmationPayload())
    window.$message.success('Password updated successfully.')
    await router.replace({ name: 'login' })
  } catch (error) {
    window.$message.error(formatApiError(error))
  }
}

function buildConfirmationPayload() {
  return {
    uid: props.userId,
    token: props.userToken,
    new_password: passwordRequest.value.password
  }
}

function validateConfirmation(): true | Error {
  if (passwordRequest.value.passwordConfirm !== passwordRequest.value.password) {
    return new Error('Passwords must match')
  }
  return true
}

function setRequestStatus(status: Status, footerText: string): void {
  requestState.value.status = status
  requestState.value.footerText = footerText
}

defineExpose({ openRequestModal })
</script>

<style scoped>
.reset-status {
  height: auto;
  justify-content: center;
  min-height: 28px;
  padding-block: 6px;
  white-space: normal;
  width: 100%;
}

.reset-status :deep(.n-tag__content) {
  line-height: 1.4;
  overflow-wrap: anywhere;
  text-align: center;
  white-space: normal;
}
</style>
