<template>
  <n-flex justify="center" align="center" class="invite-page">
    <n-card title="Create your AW Center account" class="invite-card">
      <n-spin :show="loading">
        <n-alert v-if="errorMessage" type="error" title="Invitation unavailable">
          {{ errorMessage }}
        </n-alert>
        <n-space v-else-if="context" vertical size="large">
          <n-alert type="info" :bordered="false">
            This invitation is for {{ context.email }} and expires {{ formattedExpiry }}.
          </n-alert>
          <n-alert v-if="authenticated" type="warning">
            Sign out or open this link in a private browser window before registering.
          </n-alert>
          <n-form ref="form" :model="account" :rules="rules" label-placement="top">
            <n-grid cols="2" x-gap="12">
              <n-form-item-gi label="Email">
                <n-input :value="context.email" disabled />
              </n-form-item-gi>
              <n-form-item-gi label="Username" path="username">
                <n-input v-model:value="account.username" autocomplete="username" />
              </n-form-item-gi>
              <n-form-item-gi label="First name" path="first_name">
                <n-input v-model:value="account.first_name" autocomplete="given-name" />
              </n-form-item-gi>
              <n-form-item-gi label="Last name" path="last_name">
                <n-input v-model:value="account.last_name" autocomplete="family-name" />
              </n-form-item-gi>
              <n-form-item-gi label="Password" path="password">
                <n-input
                  v-model:value="account.password"
                  type="password"
                  show-password-on="mousedown"
                  autocomplete="new-password"
                />
              </n-form-item-gi>
              <n-form-item-gi label="Confirm password" path="password_confirm">
                <n-input
                  v-model:value="account.password_confirm"
                  type="password"
                  show-password-on="mousedown"
                  autocomplete="new-password"
                />
              </n-form-item-gi>
            </n-grid>
          </n-form>
          <n-button
            type="primary"
            block
            :loading="submitting"
            :disabled="authenticated"
            @click="register"
          >
            Create account
          </n-button>
        </n-space>
        <n-button v-if="errorMessage" block style="margin-top: 16px" @click="goToLogin">
          Go to sign in
        </n-button>
      </n-spin>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInst, FormRules } from 'naive-ui'
import { validateForm } from '@/composables/forms'
import { formatApiError } from '@/services/apiError'
import {
  acceptUserInvitation,
  inspectUserInvitation,
  type InvitationAccount,
  type InvitationContext
} from '@/services/userInvitations'
import { isAuthenticated } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const form = ref<FormInst | null>(null)
const loading = ref(true)
const submitting = ref(false)
const errorMessage = ref('')
const context = ref<InvitationContext | null>(null)
const token = ref('')
const authenticated = isAuthenticated()
const account = ref<Omit<InvitationAccount, 'token'>>({
  username: '',
  first_name: '',
  last_name: '',
  password: '',
  password_confirm: ''
})
const rules: FormRules = {
  username: [{ required: true, min: 3, message: 'Enter at least 3 characters.' }],
  first_name: [{ required: true, message: 'First name is required.' }],
  last_name: [{ required: true, message: 'Last name is required.' }],
  password: [{ required: true, min: 8, message: 'Enter at least 8 characters.' }],
  password_confirm: [
    { required: true, message: 'Confirm your password.' },
    {
      validator: (_rule, value) => value === account.value.password,
      message: 'Passwords do not match.',
      trigger: ['blur', 'input']
    }
  ]
}
const formattedExpiry = computed(() => {
  if (!context.value) return ''
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(context.value.expires_at)
  )
})

onMounted(loadInvitation)

async function loadInvitation(): Promise<void> {
  token.value = route.hash.startsWith('#') ? route.hash.slice(1) : ''
  if (!token.value) {
    errorMessage.value = 'The invitation token is missing.'
    loading.value = false
    return
  }
  try {
    context.value = await inspectUserInvitation(token.value)
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    loading.value = false
  }
}

async function register(): Promise<void> {
  if (!(await validateForm(form.value))) return
  submitting.value = true
  try {
    await acceptUserInvitation({ token: token.value, ...account.value })
    window.history.replaceState(null, '', '/app/login')
    window.$message.success('Account created. Sign in with your new credentials.')
    await router.replace({ name: 'login' })
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    submitting.value = false
  }
}

async function goToLogin(): Promise<void> {
  await router.replace({ name: 'login' })
}
</script>

<style scoped>
.invite-page {
  min-height: 90vh;
  padding: 24px;
}
.invite-card {
  max-width: 720px;
  width: 100%;
}
</style>
