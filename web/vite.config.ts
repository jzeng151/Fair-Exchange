import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // Live FEX builds its picker from the official demo scenarios (#124), which live outside web/.
  // Allow exactly that folder besides the app itself; everything else outside web/ stays blocked.
  server: { fs: { allow: ['.', '../eval/scenarios'] } },
})
