<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useThemeVars } from 'naive-ui'
import PasswordPopup from '@/features/session/components/settings/PasswordPopup.vue'
import { useSessionStore } from '@/features/session/stores/session'
import { applyPreferredTheme } from '@/app/services/theme'
import type { IPreferences } from '@/features/session/models/auth'

const router = useRouter()
const store = useSessionStore()
const themeVars = useThemeVars()
const passwordPopup = ref<InstanceType<typeof PasswordPopup>>()
const saving = ref(false)
const selectedTheme = ref(store.getPreferences.theme || 'system')
const name = computed(
  () =>
    [store.getUser.first_name, store.getUser.last_name].filter(Boolean).join(' ') ||
    store.getUser.username ||
    'Account'
)
const initials = computed(() =>
  name.value
    .split(/\s+/)
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
)
const themes = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' }
] as const
const languages = [
  { label: 'English', value: 'en' },
  { label: 'Türkçe (coming soon)', value: 'tr', disabled: true }
]

async function updatePreference(preference: IPreferences) {
  if (saving.value) return
  saving.value = true
  try {
    await store.updatePreference(preference)
    if (preference.theme) applyPreferredTheme(store.getPreferences)
  } catch {
    // The store reports the error; controls continue to show saved preferences.
  } finally {
    selectedTheme.value = store.getPreferences.theme || 'system'
    saving.value = false
  }
}

async function logoutAction() {
  try {
    await store.logout()
    await router.push({ name: 'login' })
  } catch {
    // Keep the authenticated UI when server-side logout fails.
  }
}
</script>

<template>
  <div
    class="settings-page"
    :style="{
      '--settings-surface': themeVars.cardColor,
      '--settings-line': themeVars.borderColor,
      '--settings-muted': themeVars.textColor3
    }"
  >
    <header class="settings-heading">
      <h1>Settings</h1>
      <p>Manage your account and make AW Center work for you.</p>
    </header>

    <div class="settings-workspace">
      <aside class="account-panel" aria-labelledby="account-heading">
        <div class="account-avatar" aria-hidden="true">{{ initials }}</div>
        <h2 id="account-heading">{{ name }}</h2>
        <p class="account-handle" v-if="store.getUser.username">@{{ store.getUser.username }}</p>
        <dl class="account-details">
          <div>
            <dt>Email address</dt>
            <dd>{{ store.getUser.email || 'Not provided' }}</dd>
          </div>
          <div>
            <dt>Username</dt>
            <dd>{{ store.getUser.username || 'Not provided' }}</dd>
          </div>
        </dl>
        <a class="account-link" href="#account-security"
          >Account security <span aria-hidden="true">→</span></a
        >
      </aside>

      <div class="settings-sections">
        <section class="settings-section" aria-labelledby="appearance-heading">
          <header class="section-heading">
            <h2 id="appearance-heading">Appearance</h2>
            <p>Choose how your workspace looks and feels.</p>
          </header>
          <fieldset class="theme-fieldset" :disabled="saving">
            <legend>Color theme</legend>
            <div class="theme-options">
              <label
                v-for="theme in themes"
                :key="theme.value"
                class="theme-option"
                :class="{ selected: (store.getPreferences.theme || 'system') === theme.value }"
              >
                <input
                  type="radio"
                  name="theme"
                  :value="theme.value"
                  v-model="selectedTheme"
                  @change="updatePreference({ theme: theme.value })"
                />
                <span class="theme-preview" :class="`preview-${theme.value}`" aria-hidden="true"
                  ><span class="preview-sidebar"></span
                  ><span class="preview-content"><i></i><i></i><i></i></span
                ></span>
                <span class="theme-label">{{ theme.label }}</span>
              </label>
            </div>
          </fieldset>
          <div class="setting-row">
            <div>
              <h3 id="particles-label">Background particles</h3>
              <p>Show animated particles behind your workspace.</p>
            </div>
            <n-switch
              :value="Boolean(store.getPreferences.has_particles)"
              :disabled="saving"
              aria-labelledby="particles-label"
              @update:value="(value: boolean) => updatePreference({ has_particles: value })"
            />
          </div>
        </section>

        <section class="settings-section" aria-labelledby="language-heading">
          <div class="setting-row language-row">
            <div>
              <h2 id="language-heading">Language</h2>
              <p>Choose your interface language.</p>
            </div>
            <n-select
              class="language-select"
              :value="store.getPreferences.language || 'en'"
              :options="languages"
              :disabled="saving"
              aria-labelledby="language-heading"
              @update:value="(value: 'en' | 'tr') => updatePreference({ language: value })"
            />
          </div>
        </section>

        <section id="account-security" class="settings-section" aria-labelledby="security-heading">
          <header class="section-heading">
            <h2 id="security-heading">Account security</h2>
            <p>Manage your password and current session.</p>
          </header>
          <div class="setting-row">
            <div>
              <h3>Password</h3>
              <p>Update the password you use to sign in.</p>
            </div>
            <n-button @click="passwordPopup?.openModal()">Change password</n-button>
          </div>
          <div class="setting-row">
            <div>
              <h3>Sign out</h3>
              <p>End your session on this browser.</p>
            </div>
            <n-button
              secondary
              type="error"
              :loading="store.loading && !saving"
              :disabled="store.loading"
              @click="logoutAction"
              >Sign out</n-button
            >
          </div>
        </section>
      </div>
    </div>
    <PasswordPopup ref="passwordPopup" />
  </div>
</template>

<style scoped>
.settings-page {
  max-width: 1120px;
  margin: 24px auto 48px;
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
}
.settings-heading {
  padding-bottom: 32px;
  border-bottom: 1px solid var(--settings-line);
  margin-bottom: 32px;
}
h1,
h2,
h3,
p {
  margin: 0;
}
h1 {
  font-size: clamp(30px, 4vw, 42px);
  font-weight: 600;
  letter-spacing: -1.5px;
  line-height: 1.2;
}
.settings-heading p {
  margin-top: 12px;
  font-size: 15px;
}
p,
dt {
  color: var(--settings-muted);
  line-height: 1.6;
}
.settings-workspace {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 40px;
  align-items: start;
}
.account-panel {
  padding: 28px 24px;
  background: var(--settings-surface);
  border: 1px solid var(--settings-line);
  border-top: 3px solid #002fa7;
}
.account-avatar {
  width: 64px;
  height: 64px;
  display: grid;
  place-items: center;
  background: #002fa7;
  color: #fff;
  font-size: 23px;
  font-weight: 600;
  margin-bottom: 20px;
  border-radius: 50%;
}
h2 {
  font-size: 19px;
  font-weight: 600;
  letter-spacing: -0.4px;
}
.account-panel h2,
.account-handle,
dd {
  overflow-wrap: anywhere;
}
.account-handle {
  margin-top: 4px;
}
.account-details {
  margin: 28px 0;
  display: grid;
  gap: 20px;
}
dt {
  font-size: 12px;
}
dd {
  margin: 4px 0 0;
  font-size: 14px;
}
.account-link {
  border-top: 1px solid var(--settings-line);
  padding-top: 20px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: inherit;
  text-decoration: none;
  font-size: 13px;
}
.account-link:hover {
  text-decoration: underline;
}
.settings-sections {
  display: grid;
  gap: 20px;
  min-width: 0;
}
.settings-section {
  background: var(--settings-surface);
  border: 1px solid var(--settings-line);
  padding: 26px 28px;
  scroll-margin-top: 24px;
}
.section-heading p {
  margin-top: 4px;
  font-size: 13px;
}
.theme-fieldset {
  border: 0;
  padding: 0;
  margin: 24px 0;
  min-width: 0;
}
.theme-fieldset legend {
  font-size: 13px;
  margin-bottom: 12px;
}
.theme-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.theme-option {
  position: relative;
  cursor: pointer;
  border: 1px solid var(--settings-line);
  padding: 8px;
  border-radius: 6px;
}
.theme-option.selected {
  border-color: #002fa7;
  box-shadow: 0 0 0 1px #002fa7;
}
.theme-option:focus-within {
  outline: 2px solid #002fa7;
  outline-offset: 4px;
}
.theme-option input {
  position: absolute;
  bottom: 14px;
  right: 10px;
  accent-color: #002fa7;
}
.theme-preview {
  display: flex;
  gap: 8px;
  height: 76px;
  padding: 9px;
  background: #f7f7f8;
  border: 1px solid #ddd;
  border-radius: 3px;
}
.preview-sidebar {
  width: 24%;
  background: #ddd;
  border-radius: 2px;
}
.preview-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding-top: 5px;
}
.preview-content i {
  height: 6px;
  background: #ddd;
  border-radius: 2px;
}
.preview-content i:first-child {
  width: 55%;
  background: #002fa7;
}
.preview-dark {
  background: #202024;
  border-color: #444;
}
.preview-dark .preview-sidebar,
.preview-dark i:not(:first-child) {
  background: #45454b;
}
.preview-system {
  background: linear-gradient(90deg, #f7f7f8 50%, #202024 50%);
}
.theme-label {
  display: block;
  padding: 9px 22px 2px 2px;
  font-size: 13px;
}
.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 22px 0;
  border-top: 1px solid var(--settings-line);
}
.setting-row:last-child {
  padding-bottom: 0;
}
.section-heading + .setting-row {
  margin-top: 22px;
}
h3 {
  font-size: 14px;
  font-weight: 500;
}
.setting-row p {
  font-size: 13px;
  margin-top: 4px;
}
.setting-row > :last-child {
  flex-shrink: 0;
}
.language-row {
  padding-top: 0;
  border: 0;
}
.language-select {
  width: 180px;
}
@media (max-width: 1100px) {
  .settings-workspace {
    grid-template-columns: 220px minmax(0, 1fr);
    gap: 24px;
  }
}
@media (max-width: 760px) {
  .settings-page {
    margin-top: 8px;
  }
  .settings-workspace {
    grid-template-columns: minmax(0, 1fr);
    gap: 20px;
  }
  .settings-heading {
    padding-bottom: 24px;
    margin-bottom: 24px;
  }
  .account-details {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .settings-section {
    padding: 22px 18px;
  }
  .setting-row {
    flex-wrap: wrap;
    gap: 14px;
  }
  .theme-options {
    gap: 8px;
  }
  .theme-preview {
    height: 64px;
    padding: 6px;
  }
  .language-select {
    width: 100%;
  }
}
@media (max-width: 480px) {
  .settings-heading {
    padding-top: 40px;
  }
  .account-details {
    grid-template-columns: minmax(0, 1fr);
  }
  .theme-options {
    grid-template-columns: minmax(0, 1fr);
  }
  .theme-option {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .theme-preview {
    width: 70px;
    height: 48px;
    flex-shrink: 0;
  }
  .theme-label {
    padding: 0 24px 0 0;
  }
  .theme-option input {
    bottom: auto;
    top: 50%;
    margin: 0;
    transform: translateY(-50%);
  }
}
</style>
