import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

const groupedVendorChunks: Record<string, string> = {
  vue: 'vendor-vue',
  'vue-router': 'vendor-vue',
  pinia: 'vendor-vue',
  'chart.js': 'vendor-charts',
  'vue-chartjs': 'vendor-charts',
  axios: 'vendor-http',
  'markdown-it': 'vendor-markdown'
}

/**
 * Keeps route chunks readable and separates large shared vendor libraries.
 */
function createManualChunk(moduleIdentifier: string) {
  const packageName = getNodeModulePackageName(moduleIdentifier)
  if (!packageName) return undefined

  return groupedVendorChunks[packageName] ?? `vendor-${sanitizeChunkName(packageName)}`
}

function getNodeModulePackageName(moduleIdentifier: string) {
  const packagePath = moduleIdentifier.split('/node_modules/')[1]
  if (!packagePath) return ''

  const parts = packagePath.split('/')
  return parts[0].startsWith('@') ? `${parts[0]}/${parts[1]}` : parts[0]
}

function sanitizeChunkName(packageName: string) {
  return packageName.replace('@', '').replace('/', '-')
}

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  loadEnv(mode, process.cwd(), '')

  return {
    plugins: [vue()],
    base: mode == 'development' ? './' : '/core/',
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
      rollupOptions: {
        output: {
          manualChunks: createManualChunk
        }
      }
    }
  }
})
