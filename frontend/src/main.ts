import { createApp } from 'vue'
import App from './App.vue'
import naive from 'naive-ui'
import { createPinia } from "pinia"
import router from './router'

import './assets/main.css'
import { useUserStore } from './stores/user'
import { bootstrapHttpAuth } from './services/http'
import { registerChartPlugins } from './stores/chartStore'

const pinia = createPinia()
const app = createApp(App)
app.use(pinia)
app.use(router)
app.use(naive)

registerChartPlugins()

function getPreferredTheme(systemTheme: string) {
    const storedTheme = useUserStore().getPreferences.theme
    return typeof storedTheme === 'string' ? storedTheme : systemTheme
}

async function init() {
    bootstrapHttpAuth()
    const userStore = useUserStore()
    const isLoaded = await userStore.fetchCurrentUser({
        allowCachedFallback: true,
        suppressAuthenticationWarning: true
    })
    if (!isLoaded) router.push({ name: "login" })

    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? "dark" : "light"
    document.documentElement.setAttribute('data-theme', getPreferredTheme(systemTheme))
    app.mount('#app')
}

init()









