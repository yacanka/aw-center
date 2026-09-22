<script setup lang="ts">
import { ref } from 'vue'
import {
  NFormItem,
  lightTheme,
  type FormInst,
  type FormRules,
  type GlobalThemeOverrides
} from 'naive-ui'
import { useRouter, useRoute } from 'vue-router'
import { validateForm } from '@/shared/composables/forms'
import { useSessionStore } from '@/features/session/stores/session'
import { applyPreferredTheme } from '@/app/services/theme'
import PasswordRecovery from '@/features/session/components/user/PasswordRecovery.vue'
import { safePostLoginPath } from '@/features/session/services/accessPolicy'
import { takePasswordResetCapability } from '@/features/session/services/passwordResetCapability'
import { USERNAME_MESSAGE, USERNAME_PATTERN } from '@/features/session/services/usernamePolicy'

const loginTheme: GlobalThemeOverrides = {
  common: {
    primaryColor: '#002FA7',
    primaryColorHover: '#00278C',
    primaryColorPressed: '#002170',
    primaryColorSuppl: '#002FA7',
    borderRadius: '6px',
    fontFamily: '"Helvetica Neue", Helvetica, Arial, sans-serif'
  }
}

const route = useRoute()
const router = useRouter()

interface Credentials {
  username: string
  password: string
}

const loginCredentials = ref<Credentials>({ username: '', password: '' })

const resetCapability = takePasswordResetCapability()
const userId = resetCapability?.uid ?? ''
const userToken = resetCapability?.token ?? ''
const loginForm = ref<FormInst | null>(null)
const passwordRecovery = ref<InstanceType<typeof PasswordRecovery> | null>(null)

const userStore = useSessionStore()

const rules: FormRules = {
  username: [
    { required: true, message: 'Username required', trigger: 'blur' },
    { pattern: USERNAME_PATTERN, message: USERNAME_MESSAGE, trigger: ['input', 'blur'] }
  ],
  password: [{ required: true, message: 'Password required', trigger: 'blur' }]
}

async function handleLogin() {
  if (userStore.loading || !(await validateForm(loginForm.value))) return
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
  <n-config-provider :theme="lightTheme" :theme-overrides="loginTheme">
    <main class="login-page">
      <header class="login-brand">
        AW Center<span class="brand-dot" aria-hidden="true"></span>
      </header>
      <div class="login-layout">
        <section class="login-intro" aria-labelledby="brand-heading">
          <div class="intro-rule" aria-hidden="true"></div>
          <h1 id="brand-heading">
            AW <span class="brand-line">Center<span class="heading-dot">.</span></span>
          </h1>
          <p>Your workspace. <span class="intro-line">Everything in one place.</span></p>
        </section>
        <section class="login-panel" aria-label="Account access">
          <div v-if="userStore.status === 'unavailable'" class="session-notice" role="alert">
            <strong>Session service unavailable</strong>
            <p>AW Center could not verify your server-side session. Access remains locked.</p>
            <n-button :loading="userStore.loading" @click="retrySessionBootstrap"
              >Try again</n-button
            >
          </div>
          <template v-if="!userToken || !userId">
            <header class="form-heading">
              <h2>Welcome back</h2>
              <p>Login to your AW Center account.</p>
            </header>
            <n-form
              ref="loginForm"
              :model="loginCredentials"
              size="large"
              :rules="rules"
              label-placement="top"
              @submit.prevent="handleLogin"
            >
              <n-form-item label="Username" path="username">
                <n-input
                  v-model:value="loginCredentials.username"
                  type="text"
                  maxlength="6"
                  placeholder="Enter your registration number"
                  :input-props="{
                    autocomplete: 'username',
                    spellcheck: false,
                    'aria-label': 'Username'
                  }"
                />
              </n-form-item>
              <n-form-item label="Password" path="password">
                <n-input
                  v-model:value="loginCredentials.password"
                  type="password"
                  placeholder="Enter your password"
                  show-password-on="mousedown"
                  :input-props="{ autocomplete: 'current-password', 'aria-label': 'Password' }"
                />
              </n-form-item>
              <div class="recovery-link">
                <n-button text type="primary" @click="openPasswordRecovery"
                  >Forgot Password?</n-button
                >
              </div>
              <n-button
                block
                type="primary"
                size="large"
                attr-type="submit"
                :loading="userStore.loading"
              >
                Login
              </n-button>
            </n-form>
          </template>
          <PasswordRecovery ref="passwordRecovery" :user-id="userId" :user-token="userToken" />
        </section>
      </div>
      <footer class="login-footer">AW Center</footer>
    </main>
  </n-config-provider>
</template>

<style scoped>
.login-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  padding: 36px clamp(24px, 6vw, 96px) 24px;
  background: #f7f7f8;
  color: #202126;
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -0.7px;
}

.brand-dot {
  width: 6px;
  height: 6px;
  background: #002fa7;
}

.login-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  align-items: center;
  flex: 1;
  width: min(100%, 1080px);
  margin: 64px auto;
}

.login-intro {
  padding-right: 48px;
}

.intro-rule {
  width: 48px;
  height: 3px;
  margin-bottom: 32px;
  background: #002fa7;
}

.login-intro h1 {
  margin: 0;
  font-size: clamp(64px, 7.5vw, 108px);
  font-weight: 600;
  line-height: 0.98;
  letter-spacing: -0.065em;
}

.brand-line,
.intro-line {
  display: block;
}

.heading-dot {
  color: #002fa7;
}

.login-intro p {
  margin: 28px 0 0;
  color: #62646e;
  font-size: 18px;
  line-height: 1.65;
}

.login-panel {
  min-width: 0;
  padding: 48px;
  background: #fff;
  border: 1px solid #e3e3e8;
  border-radius: 12px;
}

.form-heading {
  margin-bottom: 32px;
}

.form-heading h2 {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -1px;
  line-height: 1.25;
}

.form-heading p {
  margin: 0;
  color: #62646e;
  font-size: 14px;
}

.recovery-link {
  display: flex;
  justify-content: flex-end;
  margin: -4px 0 28px;
}

.session-notice {
  margin-bottom: 28px;
  padding: 16px;
  border-left: 3px solid #002fa7;
  background: #f7f7f8;
  font-size: 14px;
}

.session-notice p {
  margin: 8px 0 16px;
}

.login-footer {
  border-top: 1px solid #dedee4;
  padding-top: 18px;
  color: #62646e;
  font-size: 12px;
}

@media (max-width: 760px) {
  .login-page {
    padding: 24px;
  }

  .login-layout {
    grid-template-columns: 1fr;
    gap: 36px;
    max-width: 440px;
    margin-block: 48px;
  }

  .login-intro {
    padding: 0;
  }

  .intro-rule {
    margin-bottom: 20px;
  }

  .login-intro h1 {
    font-size: clamp(48px, 12vw, 56px);
  }

  .brand-line {
    display: inline;
  }

  .login-intro p {
    margin-top: 16px;
    font-size: 16px;
  }

  .intro-line {
    display: inline;
  }

  .login-panel {
    padding: 28px 16px;
  }
}
</style>
