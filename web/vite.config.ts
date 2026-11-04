import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // The real-numbers test reads the regional fact table CSV (#8) from data/ with `?raw`, and the
  // Live FEX picker reads the official demo scenarios (#124); both live outside web/.
  // Allow exactly those folders besides the app itself; everything else outside web/ stays blocked.
  server: { fs: { allow: ['.', '../data/src/fx_data', '../eval/scenarios'] } },
})
