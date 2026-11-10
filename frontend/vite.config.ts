import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  loadEnv(mode, process.cwd(), '')

  return {
    plugins: [
      vue(),
      {
        name: 'django-preview-paths',
        configurePreviewServer(server) {
          server.middlewares.use((request, _response, next) => {
            // Django serves the SPA/PWA at /app/ and compiled assets at /core/.
            // Preview's base middleware otherwise rejects the canonical /app/ URLs.
            if (request.url?.startsWith('/app/')) {
              request.url = `${server.config.base.replace(/\/$/, '')}${request.url}`
            }
            next()
          })
        }
      }
    ],
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
