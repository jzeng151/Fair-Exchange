import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // The real-numbers test reads the regional fact table CSV (#8) from data/ with `?raw`.
  server: { fs: { allow: ['.', '../data/src/fx_data'] } },
})
