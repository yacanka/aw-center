<script setup lang="ts">
import { ref } from 'vue'
import { FormRules } from 'naive-ui'
import { useRouter, useRoute } from 'vue-router'
import { validateForm } from '@/shared/composables/forms'
import { useSessionStore } from '@/features/session/stores/session'
import { applyPreferredTheme } from '@/app/services/theme'
import PasswordRecovery from '@/features/session/components/user/PasswordRecovery.vue'
import { safePostLoginPath } from '@/features/session/services/accessPolicy'
import { takePasswordResetCapability } from '@/features/session/services/passwordResetCapability'

const route = useRoute()
const router = useRouter()

interface Credentials {
  username: string
  password: string
}

const loginCredentials = ref<Credentials>({} as Credentials)

const resetCapability = takePasswordResetCapability()
const userId = resetCapability?.uid ?? ''
const userToken = resetCapability?.token ?? ''
const loginForm = ref()
const passwordRecovery = ref<InstanceType<typeof PasswordRecovery> | null>(null)

const userStore = useSessionStore()

const rules: FormRules = {
  username: [
    { required: true, message: 'Username required', trigger: 'blur' },
    { min: 3, max: 150, message: 'Username must be between 3 and 150 characters', trigger: 'blur' }
  ],
  password: [{ required: true, message: 'Password required', trigger: 'blur' }]
}

async function handleLogin() {
  if (!(await validateForm(loginForm.value))) return
  const authenticatedUser = await userStore.login(loginCredentials.value)
  if (!authenticatedUser) return

  applyPreferredTheme(userStore.getPreferences)
  await router.replace(safePostLoginPath(route.query.redirect))
}

async function retrySessionBootstrap(): Promise<void> {
  const status = await userStore.bootstrap(true)
  if (status === 'authenticated') await router.replace({ name: 'home' })
}

function openPasswordRecovery(): void {
  passwordRecovery.value?.openRequestModal()
}
</script>

<template>
  <n-space
    vertical
    justify="center"
    align="center"
    class="login-page"
    item-style="width: 100%; min-width: 0"
  >
    <n-card
      v-if="userStore.status === 'unavailable'"
      title="Session service unavailable"
      size="small"
    >
      <p>AW Center could not verify your server-side session. Access remains locked.</p>
      <n-button :loading="userStore.loading" @click="retrySessionBootstrap">Try again</n-button>
    </n-card>
    <div v-if="!userToken || !userId">
      <n-tabs placement="top">
        <n-tab-pane name="login" tab="Login">
          <n-card title="Login" size="large">
            <n-form
              ref="loginForm"
              :model="loginCredentials"
              size="large"
              :rules="rules"
              label-placement="top"
            >
              <n-grid responsive="self" item-responsive :x-gap="12" :cols="6">
                <n-form-item-gi span="6" label="Username" path="username">
                  <n-input
                    v-model:value="loginCredentials.username"
                    type="text"
                    placeholder="Enter your registration number"
                  />
                </n-form-item-gi>
                <n-form-item-gi span="6" label="Password" path="password">
                  <n-input
                    v-model:value="loginCredentials.password"
                    type="password"
                    placeholder="Enter your password"
                    show-password-on="mousedown"
                  />
                </n-form-item-gi>
                <n-form-item-gi span="0:6 420:4">
                  <n-button type="primary" attr-type="submit" @click="handleLogin">Login</n-button>
                </n-form-item-gi>
                <n-form-item-gi span="0:6 420:2">
                  <n-tag checkable @click="openPasswordRecovery"> Forgot Password? </n-tag>
                </n-form-item-gi>
              </n-grid>
            </n-form>
          </n-card>
        </n-tab-pane>
      </n-tabs>
    </div>
    <PasswordRecovery ref="passwordRecovery" :user-id="userId" :user-token="userToken" />
  </n-space>
</template>

<style scoped>
.login-page {
  margin-inline: auto;
  min-height: 100dvh;
  padding: var(--app-gutter);
  width: min(100%, 480px);
}
</style>
