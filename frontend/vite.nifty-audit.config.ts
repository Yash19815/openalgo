import { defineConfig } from 'vite'
import base from './vite.config'

// Offline browser tests must never proxy to an operator's running Flask server.
export default defineConfig({
  ...base,
  server: { ...base.server, host: '127.0.0.1', port: 5199, strictPort: true, proxy: {} },
})
