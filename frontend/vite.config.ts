import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  loadEnv(mode, process.cwd(), '')

  return {
    plugins: [vue()],
    define:
      mode === 'test'
        ? {
            'import.meta.env.VITE_API_URL': JSON.stringify('/')
          }
        : undefined,
    base: mode == 'development' ? './' : '/core/',
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    build: {
      outDir: 'dist',
      assetsDir: 'assets'
    }
  }
})
