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

async function init() {
    bootstrapHttpAuth()
    try {
        await useUserStore().fetchCurrentUser()
        const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? "dark" : "light"
        document.documentElement.setAttribute('data-theme', useUserStore().getPreferences.theme || systemTheme)
    } catch (err) {
        router.push({ name: "login" })
    } finally {
        app.mount('#app')
    }
}

init()









