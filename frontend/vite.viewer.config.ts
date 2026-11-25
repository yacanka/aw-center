import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The desktop viewer ships its own entry point and has no public/PWA assets.
export default defineConfig({
  root: fileURLToPath(new URL('./src/viewer', import.meta.url)),
  publicDir: false,
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: {
    outDir: fileURLToPath(new URL('./dist-viewer', import.meta.url)),
    emptyOutDir: true
  }
})
